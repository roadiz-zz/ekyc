"""
身分証OCR ウェブアプリ（Streamlit）
"""

import json
import os
import sys
import tempfile
import time

import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

# id_ocr.py と同じディレクトリに配置されている前提
sys.path.insert(0, os.path.dirname(__file__))
from id_ocr import (
    DRIVER_LICENSE_REGIONS,
    MY_NUMBER_REGIONS,
    process_id_card,
)

st.set_page_config(page_title="身分証OCR", page_icon="🪪", layout="wide", initial_sidebar_state="collapsed")

# ── カメラをフルスクリーン表示 ────────────────────────
components.html("""
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<style>
html, body, [data-testid="stAppViewContainer"] {
  width: 100vw !important;
  height: 100vh !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}
[data-testid="stAppViewContainer"] > div {
  height: 100% !important;
}
/* カメラ枠を画面全体に */
[data-testid="stCameraInputWebcamStyledBox"],
[data-testid="stCameraInput"] {
  width: 100vw !important;
  height: 100vh !important;
  max-width: 100vw !important;
  max-height: 100vh !important;
}
[data-testid="stCameraInputWebcamStyledBox"] video,
[data-testid="stCameraInput"] video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
/* 他の要素を隠す */
[data-testid="stHeader"],
[data-testid="stToolbar"],
.stMarkdown,
.stInfo {
  display: none !important;
}
</style>
""", height=0)

# ── カメラキー：ページロードごとに新規生成 → 毎回アクセス許可を再確認 ──
if "cam_key" not in st.session_state:
    st.session_state["cam_key"] = str(time.time())

# ── カメラ撮影（フルスクリーン）────────────────────────────────────
camera_img = st.camera_input(
    label="",  # ラベルなし
    key=st.session_state["cam_key"],
)

# ── 撮影後の処理 ────────────────────────────────────────
if camera_img:
    img_pil = ImageOps.exif_transpose(Image.open(camera_img)).convert("RGB")
    card_type = "driver_license"

# ── 撮影後の処理 ────────────────────────────────────────
if camera_img:
    img_pil = ImageOps.exif_transpose(Image.open(camera_img)).convert("RGB")
    card_type = "driver_license"

    # 回転ボタン
    if st.button("↻ 回転"):
        st.session_state["_rotation"] = (st.session_state.get("_rotation", 0) + 90) % 360

    rotation = st.session_state.get("_rotation", 0)
    if rotation:
        img_pil = img_pil.rotate(-rotation, expand=True)

    st.image(img_pil, use_container_width=True)

    # OCR実行
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
