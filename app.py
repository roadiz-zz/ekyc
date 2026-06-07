"""
身分証OCR ウェブアプリ（Streamlit）
"""

import os
import sys
import tempfile

import cv2
import streamlit as st
from PIL import Image

# id_ocr.py と同じディレクトリに配置されている前提
sys.path.insert(0, os.path.dirname(__file__))
from id_ocr import (
    DRIVER_LICENSE_REGIONS,
    MY_NUMBER_REGIONS,
    process_id_card,
)

st.set_page_config(page_title="身分証OCR", page_icon="🪪", layout="centered")

st.title("🪪 身分証明書 OCR")
st.caption("運転免許証・マイナンバーカードから氏名・生年月日・住所を読み取ります")

# ── カード種別選択 ──────────────────────────────────────
card_type_label = st.radio(
    "カード種別",
    ["自動判定", "運転免許証", "マイナンバーカード"],
    horizontal=True,
)
card_type_map = {
    "自動判定": "auto",
    "運転免許証": "driver_license",
    "マイナンバーカード": "my_number",
}
card_type = card_type_map[card_type_label]

# ── 画像アップロード ────────────────────────────────────
uploaded = st.file_uploader("身分証の画像をアップロード", type=["jpg", "jpeg", "png"])

if uploaded:
    img_pil = Image.open(uploaded).convert("RGB")
    st.image(img_pil, caption="アップロードされた画像", use_container_width=True)

    # ── OCR実行 ────────────────────────────────────────
    if st.button("OCR実行", type="primary"):
        with st.spinner("読み取り中..."):
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
                img_pil.save(tmp_path)
            try:
                result = process_id_card(tmp_path, card_type)
                st.success("読み取り完了！")
                st.subheader("抽出結果")
                for field, value in result.items():
                    st.text_input(field, value=value)
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

    # ── 領域確認（座標調整用） ──────────────────────────
    with st.expander("OCR領域を確認する（座標調整用）"):
        ct_vis = "driver_license" if card_type == "auto" else card_type
        if st.button("領域を表示"):
            with st.spinner("処理中..."):
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = tmp.name
                    img_pil.save(tmp_path)
                try:
                    img = cv2.imread(tmp_path)
                    regions = (
                        DRIVER_LICENSE_REGIONS
                        if ct_vis == "driver_license"
                        else MY_NUMBER_REGIONS
                    )
                    h, w = img.shape[:2]
                    colors = {
                        "氏名": (0, 255, 0),
                        "生年月日": (255, 0, 0),
                        "住所": (0, 0, 255),
                    }
                    for field, region in regions.items():
                        x = int(region[0] * w)
                        y = int(region[1] * h)
                        rw = int(region[2] * w)
                        rh = int(region[3] * h)
                        color = colors.get(field, (255, 255, 0))
                        cv2.rectangle(img, (x, y), (x + rw, y + rh), color, 2)
                        cv2.putText(
                            img, field, (x, max(y - 5, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                        )
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    st.image(
                        img_rgb,
                        caption="OCR領域（緑:氏名 / 赤:生年月日 / 青:住所）",
                        use_container_width=True,
                    )
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

st.divider()
st.caption("⚠️ アップロードされた画像はサーバーに保存されません。")
