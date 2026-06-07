"""
日本の身分証明書OCRツール
対応カード：運転免許証 / マイナンバーカード
取得項目：氏名・生年月日・住所
"""

import cv2
import numpy as np
import easyocr
from PIL import Image
import re
import sys
from pathlib import Path

# EasyOCR初期化（グローバル）
_reader = easyocr.Reader(['ja'], gpu=False)


# =====================================================================
# カードレイアウト定義（座標は比率で指定: x, y, w, h / カード全体サイズ）
# 実際の画像で微調整が必要になる場合があります
# =====================================================================

DRIVER_LICENSE_REGIONS = {
    "氏名": (0.19, 0.08, 0.43, 0.10),
    "生年月日": (0.62, 0.08, 0.32, 0.10),
    "住所": (0.18, 0.22, 0.71, 0.11),
}

MY_NUMBER_REGIONS = {
    "氏名": (0.08, 0.38, 0.60, 0.10),       # 氏名欄
    "生年月日": (0.08, 0.49, 0.55, 0.09),   # 生年月日欄
    "住所": (0.08, 0.59, 0.80, 0.16),       # 住所欄
}


# =====================================================================
# 画像前処理
# =====================================================================

def preprocess_image(img: np.ndarray) -> np.ndarray:
    """傾き補正・グレースケール・二値化を行う"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 傾き検出・補正
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 10:  # 大きく傾いている場合は補正しない（誤検出防止）
            h, w = gray.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)

    # ノイズ除去 → 二値化
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def extract_region(img: np.ndarray, region: tuple) -> np.ndarray:
    """比率で指定された領域を切り出す"""
    h, w = img.shape[:2]
    x = int(region[0] * w)
    y = int(region[1] * h)
    rw = int(region[2] * w)
    rh = int(region[3] * h)
    crop = img[y:y+rh, x:x+rw]
    # OCR精度向上のため拡大
    crop = cv2.resize(crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    return crop


# =====================================================================
# OCR実行
# =====================================================================

def ocr_region(img_region: np.ndarray) -> str:
    """領域画像にEasyOCRをかける"""
    results = _reader.readtext(img_region, detail=0)
    if results:
        text = '\n'.join(results)
        return text.strip()
    return ""


# =====================================================================
# テキスト後処理
# =====================================================================

def clean_name(text: str) -> str:
    """氏名の不要文字を除去"""
    # ラベル文字除去
    text = re.sub(r'(氏名|名前|ふりがな|フリガナ)[：:\s]*', '', text)
    # 改行を空白に
    text = text.replace('\n', ' ').strip()
    return text


def clean_date(text: str) -> str:
    """生年月日を整形"""
    text = re.sub(r'(生年月日|生年|誕生日)[：:\s]*', '', text)
    # 元号パターン（昭和・平成・令和）
    m = re.search(r'(昭和|平成|令和)\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日', text)
    if m:
        return f"{m.group(1)}{m.group(2)}年{m.group(3)}月{m.group(4)}日"
    # 西暦パターン
    m = re.search(r'(\d{4})\s*[年/\-]\s*(\d{1,2})\s*[月/\-]\s*(\d{1,2})', text)
    if m:
        return f"{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return text.strip()


def clean_address(text: str) -> str:
    """住所の整形"""
    text = re.sub(r'(住所|所在地)[：:\s]*', '', text)
    # 改行をスペースに統一
    text = re.sub(r'\s+', ' ', text).strip()
    return text


CLEANERS = {
    "氏名": clean_name,
    "生年月日": clean_date,
    "住所": clean_address,
}


# =====================================================================
# カード種別判定
# =====================================================================

def detect_card_type(img: np.ndarray) -> str:
    """
    簡易判定：アスペクト比とOCRキーワードでカード種別を推定
    運転免許証: 横長 (85.6mm x 54mm) ≒ 1.58
    マイナンバーカード: 同じサイズだが表面レイアウトが異なる
    → キーワードOCRで判定する
    """
    h, w = img.shape[:2]
    # カード全体をざっくりOCRしてキーワード検索
    small = cv2.resize(img, (800, int(800 * h / w)))
    ocr_results = _reader.readtext(small, detail=0)
    full_text = '\n'.join(ocr_results) if ocr_results else ""

    if "免許" in full_text or "運転" in full_text:
        return "driver_license"
    elif "個人番号" in full_text or "マイナンバー" in full_text or "氏名" in full_text:
        return "my_number"
    else:
        # デフォルトは免許証として処理
        print("⚠️  カード種別を自動判定できませんでした。運転免許証として処理します。")
        return "driver_license"


# =====================================================================
# メイン処理
# =====================================================================

def process_id_card(image_path: str, card_type: str = "auto") -> dict:
    """
    身分証画像からOCRで情報を抽出する

    Args:
        image_path: 画像ファイルパス
        card_type: "driver_license" / "my_number" / "auto"

    Returns:
        {"氏名": ..., "生年月日": ..., "住所": ...}
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"画像を読み込めません: {image_path}")

    # カード種別判定
    if card_type == "auto":
        card_type = detect_card_type(img)
    print(f"📄 カード種別: {'運転免許証' if card_type == 'driver_license' else 'マイナンバーカード'}")

    regions = DRIVER_LICENSE_REGIONS if card_type == "driver_license" else MY_NUMBER_REGIONS

    # 前処理
    processed = preprocess_image(img)

    # 各フィールド抽出
    results = {}
    for field, region in regions.items():
        crop = extract_region(processed, region)
        raw_text = ocr_region(crop)
        cleaned = CLEANERS[field](raw_text)
        results[field] = cleaned
        print(f"  {field}: {cleaned}")

    return results


# =====================================================================
# デバッグ用：領域可視化
# =====================================================================

def visualize_regions(image_path: str, card_type: str = "driver_license"):
    """指定した領域を画像上に描画して確認用に保存"""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"画像を読み込めません: {image_path}")

    h, w = img.shape[:2]
    regions = DRIVER_LICENSE_REGIONS if card_type == "driver_license" else MY_NUMBER_REGIONS
    colors = {"氏名": (0, 255, 0), "生年月日": (255, 0, 0), "住所": (0, 0, 255)}

    for field, region in regions.items():
        x = int(region[0] * w)
        y = int(region[1] * h)
        rw = int(region[2] * w)
        rh = int(region[3] * h)
        color = colors.get(field, (255, 255, 0))
        cv2.rectangle(img, (x, y), (x + rw, y + rh), color, 2)
        cv2.putText(img, field, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    out_path = Path(image_path).stem + "_regions.jpg"
    cv2.imwrite(out_path, img)
    print(f"✅ 領域可視化画像を保存しました: {out_path}")


# =====================================================================
# CLI
# =====================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方:")
        print("  python id_ocr.py <画像パス> [driver_license|my_number|auto]")
        print("  python id_ocr.py <画像パス> visualize [driver_license|my_number]")
        sys.exit(1)

    image_path = sys.argv[1]

    if len(sys.argv) >= 3 and sys.argv[2] == "visualize":
        card_type = sys.argv[3] if len(sys.argv) >= 4 else "driver_license"
        visualize_regions(image_path, card_type)
    else:
        card_type = sys.argv[2] if len(sys.argv) >= 3 else "auto"
        print(f"\n🔍 OCR開始: {image_path}\n")
        result = process_id_card(image_path, card_type)
        print("\n========== 抽出結果 ==========")
        for k, v in result.items():
            print(f"  {k}: {v}")
        print("================================\n")
