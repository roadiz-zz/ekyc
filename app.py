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
from streamlit_js_eval import streamlit_js_eval

# id_ocr.py と同じディレクトリに配置されている前提
sys.path.insert(0, os.path.dirname(__file__))
from id_ocr import (
    DRIVER_LICENSE_REGIONS,
    MY_NUMBER_REGIONS,
    process_id_card,
)

st.set_page_config(page_title="身分証OCR", page_icon="🪪", layout="centered")

# ── カメラキー：ページロードごとに新規生成 → 毎回アクセス許可を再確認 ──
if "cam_key" not in st.session_state:
    st.session_state["cam_key"] = str(time.time())

# ── デバイス判定（screen.width < 768 → スマホ） ──────────────
screen_width = streamlit_js_eval(js_expressions="screen.width", key="sw")
is_mobile = (screen_width is not None) and (int(screen_width) < 768)

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
    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("↺ カメラ再起動", help="カメラのアクセス許可を再確認します"):
            st.session_state["cam_key"] = str(time.time())
            st.rerun()
    camera_img = st.camera_input(
        "カメラで身分証を撮影",
        key=st.session_state["cam_key"],
    )

    # OCRガイド枠をカメラプレビューにオーバーレイ
    _ct = card_type if card_type != "auto" else "driver_license"
    _regions = DRIVER_LICENSE_REGIONS if _ct == "driver_license" else MY_NUMBER_REGIONS
    _regions_js = json.dumps({
        name: {"x": x, "y": y, "w": w, "h": h}
        for name, (x, y, w, h) in _regions.items()
    })
    _colors_js = json.dumps({"氏名": "#44ff44", "生年月日": "#ff5555", "住所": "#55aaff"})
    _mobile_js = "true" if is_mobile else "false"
    components.html(f"""
<script>
(function() {{
  const regions = {_regions_js};
  const colors  = {_colors_js};
  const isMobile = {_mobile_js};

  function getVideo() {{
    return window.parent.document.querySelector('[data-testid="stCameraInput"] video');
  }}

  function getOrCreateCanvas(video) {{
    const doc = window.parent.document;
    const parent = video.parentElement;
    parent.style.position = 'relative';
    let c = doc.getElementById('ocr-guide-canvas');
    if (!c) {{
      c = doc.createElement('canvas');
      c.id = 'ocr-guide-canvas';
      c.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:10;';
      parent.appendChild(c);
    }}
    return c;
  }}

  function draw() {{
    try {{
      const video = getVideo();
      if (!video || !video.videoWidth) return;
      const canvas = getOrCreateCanvas(video);
      const W = canvas.offsetWidth, H = canvas.offsetHeight;
      canvas.width = W; canvas.height = H;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, W, H);

      // 映像の実際の描画領域（レターボックス考慮）
      const vAR = video.videoWidth / video.videoHeight;
      const cAR = W / H;
      let vx, vy, vw, vh;
      if (vAR > cAR) {{ vw=W; vh=W/vAR; vx=0; vy=(H-vh)/2; }}
      else            {{ vh=H; vw=H*vAR; vx=(W-vw)/2; vy=0; }}

      // カード枠とOCR枠の描画
      const cardAR = 85.6/54;
      let cx, cy, cw, ch;

      if (isMobile) {{
        // スマホ（縦）: カメラの縦比率に合わせた縦長ガイド枠のみ表示
        ch = vh * 0.88;
        cw = ch / cardAR;
        if (cw > vw * 0.9) {{ cw = vw * 0.9; ch = cw * cardAR; }}
        cx = vx + (vw - cw) / 2;
        cy = vy + (vh - ch) / 2;
        ctx.strokeStyle = 'rgba(255,255,255,0.75)';
        ctx.lineWidth = 2; ctx.setLineDash([8,4]);
        ctx.strokeRect(cx, cy, cw, ch);
        ctx.setLineDash([]);
        ctx.font = 'bold 12px sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.7)';
        ctx.textAlign = 'center';
        ctx.fillText('カードをここに合わせてください', cx + cw/2, cy + ch + 18);
        ctx.textAlign = 'left';
      }} else {{
        // PC（横）: ランドスケープ枠 + OCR領域ボックス
        cw = vw*0.92; ch = cw/cardAR;
        if (ch > vh*0.9) {{ ch=vh*0.9; cw=ch*cardAR; }}
        cx = vx+(vw-cw)/2; cy = vy+(vh-ch)/2;
        ctx.strokeStyle='rgba(255,255,255,0.75)';
        ctx.lineWidth=2; ctx.setLineDash([8,4]);
        ctx.strokeRect(cx, cy, cw, ch);
        ctx.setLineDash([]);

        for (const [name, r] of Object.entries(regions)) {{
          const rx = cx + r.x*cw, ry = cy + r.y*ch;
          const rw = r.w*cw,      rh = r.h*ch;
          ctx.strokeStyle = colors[name]||'#fff';
          ctx.lineWidth = 2;
          ctx.strokeRect(rx, ry, rw, rh);
          ctx.font = 'bold 11px sans-serif';
          const tw = ctx.measureText(name).width;
          ctx.fillStyle = 'rgba(0,0,0,0.55)';
          ctx.fillRect(rx, ry-16, tw+6, 16);
          ctx.fillStyle = colors[name]||'#fff';
          ctx.fillText(name, rx+3, ry-3);
        }}
      }}
    }} catch(e) {{}}
  }}

  function loop() {{ draw(); requestAnimationFrame(loop); }}
  setTimeout(loop, 600);
}})();
</script>
""", height=0)

with tab_upload:
    uploaded = st.file_uploader("身分証の画像をアップロード", type=["jpg", "jpeg", "png"])

# どちらかの入力を使用
raw_input = camera_img or uploaded

if raw_input:
    img_pil = ImageOps.exif_transpose(Image.open(raw_input)).convert("RGB")

    # スマホのカメラ撮影は縦長 → 90°回転して横長（OCR基準方向）に正規化
    if raw_input is camera_img and is_mobile:
        w, h = img_pil.size
        if h > w:
            img_pil = img_pil.rotate(-90, expand=True)

    # 回転ボタン（同じ画像が選択されている間、回転角度を保持）
    img_key = getattr(raw_input, "name", "") + str(getattr(raw_input, "size", ""))
    if st.session_state.get("_last_img_key") != img_key:
        st.session_state["_rotation"] = 0
        st.session_state["_last_img_key"] = img_key

    col_img, col_rot = st.columns([5, 1])
    with col_rot:
        st.write("")
        if st.button("↻ 回転", help="90°回転します"):
            st.session_state["_rotation"] = (st.session_state.get("_rotation", 0) + 90) % 360

    rotation = st.session_state.get("_rotation", 0)
    if rotation:
        img_pil = img_pil.rotate(-rotation, expand=True)

    with col_img:
        st.image(img_pil, caption="撮影・アップロードされた画像", use_container_width=True)

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
