"""
身分証OCR ウェブアプリ（Streamlit）
"""

import os
import sys
import tempfile

import cv2
import numpy as np
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

# ── 画像入力（カメラ / アップロード） ────────────────────
tab_cam, tab_upload = st.tabs(["📷 カメラで撮影", "📁 ファイルをアップロード"])

with tab_cam:
    camera_img = st.camera_input("カメラで身分証を撮影")

with tab_upload:
    uploaded = st.file_uploader("身分証の画像をアップロード", type=["jpg", "jpeg", "png"])

# どちらかの入力を使用
raw_input = camera_img or uploaded

if raw_input:
    img_pil = Image.open(raw_input).convert("RGB")
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

    # ── 座標調整モード ──────────────────────────────────
    with st.expander("🔧 座標調整モード（ずれている場合はここで調整）"):
        ct_vis = "driver_license" if card_type == "auto" else card_type
        default_regions = (
            DRIVER_LICENSE_REGIONS if ct_vis == "driver_license" else MY_NUMBER_REGIONS
        )
        colors = {"氏名": (0, 255, 0), "生年月日": (255, 0, 0), "住所": (0, 0, 255)}

        st.caption("スライダーを動かして枠の位置・サイズを調整してください。")
        adjusted = {}
        for field, (dx, dy, dw, dh) in default_regions.items():
            color_name = {"氏名": "🟩", "生年月日": "🟥", "住所": "🟦"}[field]
            st.markdown(f"**{color_name} {field}**")
            col1, col2 = st.columns(2)
            with col1:
                nx = st.slider(f"X（左端）", 0.0, 0.95, dx, 0.01, key=f"{field}_x")
                ny = st.slider(f"Y（上端）", 0.0, 0.95, dy, 0.01, key=f"{field}_y")
            with col2:
                nw = st.slider(f"W（幅）", 0.01, 1.0, dw, 0.01, key=f"{field}_w")
                nh = st.slider(f"H（高さ）", 0.01, 0.5, dh, 0.01, key=f"{field}_h")
            adjusted[field] = (nx, ny, nw, nh)

        # スライダーの値でリアルタイム描画
        img_np = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        h, w = img_np.shape[:2]
        for field, (nx, ny, nw, nh) in adjusted.items():
            x = int(nx * w); y = int(ny * h)
            rw = int(nw * w); rh = int(nh * h)
            color = colors[field]
            cv2.rectangle(img_np, (x, y), (x + rw, y + rh), color, 2)
            cv2.putText(img_np, field, (x, max(y - 5, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        st.image(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB),
                 caption="調整中の領域（緑:氏名 / 赤:生年月日 / 青:住所）",
                 use_container_width=True)

        # コピー用コード表示
        st.markdown("**調整後の座標（`id_ocr.py` に貼り付けてください）**")
        card_var = "DRIVER_LICENSE_REGIONS" if ct_vis == "driver_license" else "MY_NUMBER_REGIONS"
        code_lines = [f"{card_var} = {{"]
        for field, (nx, ny, nw, nh) in adjusted.items():
            code_lines.append(f'    "{field}": ({nx:.2f}, {ny:.2f}, {nw:.2f}, {nh:.2f}),')
        code_lines.append("}")
        st.code("\n".join(code_lines), language="python")

st.divider()
st.caption("⚠️ アップロードされた画像はサーバーに保存されません。")
