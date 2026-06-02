"""动画引擎：60fps 调度器 + 弹簧物理 + 果冻交互效果 - TDesign 风格"""

import math
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk
from app.constants import (
    TD_BRAND, TD_BRAND_HOVER, TD_BRAND_LIGHT, TD_BRAND_FOCUS,
    TD_SUCCESS, TD_BORDER_LEVEL1, TD_BORDER_LEVEL2,
    TD_TEXT_PLACEHOLDER,
)


# ======================================================================
# 颜色工具
# ======================================================================
class ColorUtils:
    """十六进制颜色解析与插值"""

    @staticmethod
    def parse_hex(hex_str: str):
        h = hex_str.lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def to_hex(r: int, g: int, b: int) -> str:
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"

    @staticmethod
    def lerp(color_a: str, color_b: str, t: float) -> str:
        """线性插值，t 可超出 [0,1]（弹簧过冲时自动 clamp 到 [0,255]）"""
        r1, g1, b1 = ColorUtils.parse_hex(color_a)
        r2, g2, b2 = ColorUtils.parse_hex(color_b)
        t = max(0.0, min(1.0, t))  # clamp t for color
        r = round(r1 + (r2 - r1) * t)
        g = round(g1 + (g2 - g1) * t)
        b = round(b1 + (b2 - b1) * t)
        return ColorUtils.to_hex(r, g, b)


# ======================================================================
# 缓动函数
# ======================================================================
class Easing:
    """纯函数，输入归一化时间 t∈[0,1]，输出进度值（弹簧可 >1 或 <0）"""

    @staticmethod
    def spring(t: float, damping: float = 6.0, freq: float = 14.0) -> float:
        """阻尼振荡：1 - e^(-d*t) * cos(f*t)"""
        return 1.0 - math.exp(-damping * t) * math.cos(freq * t)

    @staticmethod
    def jelly(t: float, squish: float = 0.15) -> float:
        """两段式果冻：前 15% 压缩 + 后 85% 弹簧回弹"""
        if t < squish:
            # 压缩阶段：0 → -peak（ease-in 二次曲线）
            p = t / squish
            return -(p * p)  # 向下压缩
        else:
            # 回弹阶段：弹簧从 -peak 回到 1
            p = (t - squish) / (1.0 - squish)
            return Easing.spring(p)

    @staticmethod
    def ease_out_cubic(t: float) -> float:
        return 1.0 - (1.0 - t) ** 3

    @staticmethod
    def ease_in_cubic(t: float) -> float:
        return t ** 3

    @staticmethod
    def ease_in_out_quad(t: float) -> float:
        return 2 * t * t if t < 0.5 else 1.0 - (-2 * t + 2) ** 2 / 2

    @staticmethod
    def triangle_pulse(t: float) -> float:
        """对称三角波：0→1→0，峰值在 t=0.5"""
        return 1.0 - abs(2 * t - 1)


# ======================================================================
# 动画调度器 —— 单一 60fps 循环管理所有并发动画
# ======================================================================
class AnimationScheduler:
    TICK_MS = 16  # ~60fps

    def __init__(self, root: tk.Misc):
        self._root = root
        self._active: dict[str, dict] = {}
        self._after_id: Optional[str] = None
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            self._tick()

    def stop(self):
        self._running = False
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    # ---- 公共 API ----
    def animate(
        self,
        widget,
        prop: str,
        from_val,
        to_val,
        duration_ms: int,
        easing: Callable = Easing.ease_out_cubic,
        apply_fn: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
    ):
        """启动/替换一个属性动画。同 widget+prop 的旧动画会被覆盖。"""
        key = f"{id(widget)}:{prop}"
        total_frames = max(1, duration_ms // self.TICK_MS)
        self._active[key] = {
            "widget": widget,
            "prop": prop,
            "from": from_val,
            "to": to_val,
            "frame": 0,
            "total": total_frames,
            "easing": easing,
            "apply": apply_fn,
            "on_complete": on_complete,
        }

    def cancel(self, widget, prop: str = None):
        """取消指定控件的某个或全部动画"""
        if prop:
            self._active.pop(f"{id(widget)}:{prop}", None)
        else:
            prefix = f"{id(widget)}:"
            keys = [k for k in self._active if k.startswith(prefix)]
            for k in keys:
                del self._active[k]

    # ---- 内部循环 ----
    def _tick(self):
        if not self._running:
            return
        to_remove = []
        for key, anim in self._active.items():
            widget = anim["widget"]
            anim["frame"] += 1
            t = anim["frame"] / anim["total"]  # 归一化时间
            if t >= 1.0:
                t = 1.0
                to_remove.append(key)

            progress = anim["easing"](t)
            from_val = anim["from"]
            to_val = anim["to"]

            # 插值
            if isinstance(from_val, (int, float)):
                value = from_val + (to_val - from_val) * progress
            elif isinstance(from_val, str) and from_val.startswith("#"):
                value = ColorUtils.lerp(from_val, to_val, progress)
            else:
                value = to_val

            # 应用
            apply_fn = anim["apply"]
            try:
                if apply_fn:
                    apply_fn(widget, value)
                else:
                    self._default_apply(widget, anim["prop"], value)
            except (tk.TclError, Exception):
                to_remove.append(key)

            if key in to_remove and anim["on_complete"]:
                try:
                    anim["on_complete"]()
                except Exception:
                    pass

        for key in to_remove:
            self._active.pop(key, None)

        self._after_id = self._root.after(self.TICK_MS, self._tick)

    @staticmethod
    def _default_apply(widget, prop: str, value):
        """默认应用方式：configure()"""
        if isinstance(value, float) and prop in (
            "height", "width", "border_width", "corner_radius",
        ):
            value = int(round(value))
        widget.configure(**{prop: value})


# ======================================================================
# 果冻效果 —— 高级 API
# ======================================================================
class JellyEffects:
    """为控件附加交互效果，每个方法都是幂等的。"""

    # ---- 可调参数 ----
    JELLY_DURATION = 400
    HOVER_DURATION = 150
    CARD_HOVER_DURATION = 200
    FOCUS_DURATION = 200
    DAY_SPRING_DURATION = 300
    SAVE_PULSE_DURATION = 600

    FOCUS_COLOR = TD_BRAND
    FOCUS_BORDER_WIDTH = 2
    CARD_HOVER_COLOR = "#D1FAE5"
    SAVE_PULSE_COLOR = TD_SUCCESS
    HOVER_BORDER_COLOR = TD_BRAND_FOCUS

    DEFAULT_BORDER_COLOR = TD_BORDER_LEVEL1

    # ================================================================
    # 1. 按钮果冻弹跳
    # ================================================================
    @staticmethod
    def apply_button_jelly(btn: ctk.CTkButton, animator: AnimationScheduler):
        """点击时果冻弹跳效果"""
        orig_height = btn.cget("height")
        orig_width = btn.cget("width")
        orig_cr = btn.cget("corner_radius")
        is_fill_x = False  # 运行时检测

        def _on_press(event=None):
            nonlocal is_fill_x
            try:
                if btn.cget("state") == "disabled":
                    return
            except Exception:
                return
            # 点击时实时获取当前颜色（避免侧边栏等动态改色场景的颜色冲突）
            orig_fg = btn._fg_color
            # 检测是否 fill="x"
            info = btn.pack_info()
            is_fill_x = info.get("fill", "") in ("x", "both")

            h = btn.cget("height")
            w = btn.cget("width")
            cr = btn.cget("corner_radius")

            if is_fill_x:
                # fill-x 按钮：用 corner_radius + border_width 模拟形变
                animator.animate(btn, "corner_radius", cr, max(3, cr - 3),
                                 JellyEffects.JELLY_DURATION, Easing.jelly,
                                 apply_fn=lambda w, v: w.configure(corner_radius=int(v)))
                animator.animate(btn, "border_width", 0, 3,
                                 int(JellyEffects.JELLY_DURATION * 0.4), Easing.jelly,
                                 apply_fn=lambda w, v: w.configure(border_width=int(round(v))),
                                 on_complete=lambda: _safe_configure(btn, border_width=0))
            else:
                # 固定尺寸按钮：height 压缩 + width 膨胀
                squish_h = int(h * 0.85)
                expand_w = int(w * 1.06)
                animator.animate(btn, "height", h, squish_h,
                                 int(JellyEffects.JELLY_DURATION * 0.15),
                                 Easing.ease_in_cubic,
                                 apply_fn=_make_dim_apply(btn, "height"),
                                 on_complete=lambda: animator.animate(
                                     btn, "height", squish_h, orig_height,
                                     int(JellyEffects.JELLY_DURATION * 0.85),
                                     Easing.spring,
                                     apply_fn=_make_dim_apply(btn, "height")))
                animator.animate(btn, "width", w, expand_w,
                                 int(JellyEffects.JELLY_DURATION * 0.15),
                                 Easing.ease_in_cubic,
                                 apply_fn=_make_dim_apply(btn, "width"),
                                 on_complete=lambda: animator.animate(
                                     btn, "width", expand_w, orig_width,
                                     int(JellyEffects.JELLY_DURATION * 0.85),
                                     Easing.spring,
                                     apply_fn=_make_dim_apply(btn, "width")))

            # 颜色闪烁（通过 canvas 直接操作）
            _flash_color(btn, animator, orig_fg)

        btn.bind("<Button-1>", _on_press, add="+")

    # ================================================================
    # 2. 按钮悬停抬升
    # ================================================================
    @staticmethod
    def apply_hover_lift(btn: ctk.CTkButton, animator: AnimationScheduler):
        """悬停时边框浮起效果"""
        _orig_border = btn.cget("border_color") or TD_BORDER_LEVEL1

        def _on_enter(event=None):
            try:
                if btn.cget("state") == "disabled":
                    return
            except Exception:
                return
            bw = btn.cget("border_width")
            animator.animate(btn, "border_width", bw, 2,
                             JellyEffects.HOVER_DURATION, Easing.ease_out_cubic,
                             apply_fn=_make_dim_apply(btn, "border_width"))
            _animate_border_color_fast(btn, animator,
                                       btn.cget("border_color") or _orig_border,
                                       JellyEffects.HOVER_BORDER_COLOR,
                                       JellyEffects.HOVER_DURATION)

        def _on_leave(event=None):
            bw = btn.cget("border_width")
            animator.animate(btn, "border_width", bw, 0,
                             JellyEffects.HOVER_DURATION, Easing.ease_in_cubic,
                             apply_fn=_make_dim_apply(btn, "border_width"))
            _animate_border_color_fast(btn, animator,
                                       btn.cget("border_color") or JellyEffects.HOVER_BORDER_COLOR,
                                       _orig_border,
                                       JellyEffects.HOVER_DURATION)

        btn.bind("<Enter>", _on_enter, add="+")
        btn.bind("<Leave>", _on_leave, add="+")

    # ================================================================
    # 3. 卡片悬停发光
    # ================================================================
    @staticmethod
    def apply_card_hover(card: ctk.CTkFrame, animator: AnimationScheduler):
        """鼠标进入卡片时边框发光"""
        try:
            if card.cget("border_width") == 0:
                card.configure(border_width=1, border_color="white")
        except Exception:
            pass

        _orig_border = card.cget("border_color") or TD_BORDER_LEVEL1

        def _on_enter(event=None):
            _animate_border_color_fast(
                card, animator,
                card.cget("border_color") or _orig_border,
                JellyEffects.CARD_HOVER_COLOR,
                JellyEffects.CARD_HOVER_DURATION,
            )

        def _on_leave(event=None):
            _animate_border_color_fast(
                card, animator,
                card.cget("border_color") or JellyEffects.CARD_HOVER_COLOR,
                _orig_border,
                JellyEffects.CARD_HOVER_DURATION,
            )

        card.bind("<Enter>", _on_enter, add="+")
        card.bind("<Leave>", _on_leave, add="+")

    # ================================================================
    # 4. 输入框聚焦发光
    # ================================================================
    @staticmethod
    def apply_focus_glow(widget, animator: AnimationScheduler):
        """输入框获得焦点时边框变蓝发光"""
        orig_border = JellyEffects.DEFAULT_BORDER_COLOR

        def _on_focus_in(event=None):
            bw = widget.cget("border_width")
            animator.animate(widget, "border_width", bw, JellyEffects.FOCUS_BORDER_WIDTH,
                             JellyEffects.FOCUS_DURATION, Easing.ease_out_cubic,
                             apply_fn=_make_dim_apply(widget, "border_width"))
            _animate_border_color_fast(
                widget, animator,
                widget.cget("border_color") or orig_border,
                JellyEffects.FOCUS_COLOR,
                JellyEffects.FOCUS_DURATION,
            )

        def _on_focus_out(event=None):
            bw = widget.cget("border_width")
            animator.animate(widget, "border_width", bw, 1,
                             JellyEffects.FOCUS_DURATION, Easing.ease_in_cubic,
                             apply_fn=_make_dim_apply(widget, "border_width"))
            _animate_border_color_fast(
                widget, animator,
                widget.cget("border_color") or JellyEffects.FOCUS_COLOR,
                orig_border,
                JellyEffects.FOCUS_DURATION,
            )

        widget.bind("<FocusIn>", _on_focus_in, add="+")
        widget.bind("<FocusOut>", _on_focus_out, add="+")

    # ================================================================
    # 5. 天数切换弹簧
    # ================================================================
    @staticmethod
    def trigger_day_spring(new_btn: ctk.CTkButton, old_btn: ctk.CTkButton,
                           animator: AnimationScheduler):
        """天数切换时新旧按钮的弹簧动画"""
        # 新激活按钮：放大弹回
        orig_cr = new_btn.cget("corner_radius")
        orig_h = new_btn.cget("height")
        animator.animate(new_btn, "corner_radius", max(2, orig_cr - 2), orig_cr,
                         JellyEffects.DAY_SPRING_DURATION, Easing.spring,
                         apply_fn=_make_dim_apply(new_btn, "corner_radius"))
        animator.animate(new_btn, "height", orig_h + 4, orig_h,
                         JellyEffects.DAY_SPRING_DURATION, Easing.spring,
                         apply_fn=_make_dim_apply(new_btn, "height"))

        # 旧按钮：缩小弹回
        old_h = old_btn.cget("height")
        animator.animate(old_btn, "height", max(20, old_h - 3), old_h,
                         int(JellyEffects.DAY_SPRING_DURATION * 0.7),
                         Easing.ease_out_cubic,
                         apply_fn=_make_dim_apply(old_btn, "height"))

    # ================================================================
    # 6. 保存确认脉冲
    # ================================================================
    @staticmethod
    def trigger_save_pulse(btn: ctk.CTkButton, animator: AnimationScheduler):
        """保存成功后按钮颜色闪烁绿光"""
        orig_fg = btn._fg_color
        pulse_color = JellyEffects.SAVE_PULSE_COLOR

        def _apply_color(widget, color):
            _set_btn_fg_fast(widget, color)

        # 蓝 → 绿
        animator.animate(btn, "fg_pulse", orig_fg, pulse_color,
                         JellyEffects.SAVE_PULSE_DURATION // 2,
                         Easing.ease_out_cubic,
                         apply_fn=_apply_color,
                         on_complete=lambda: animator.animate(
                             btn, "fg_pulse", pulse_color, orig_fg,
                             JellyEffects.SAVE_PULSE_DURATION // 2,
                             Easing.ease_in_cubic,
                             apply_fn=_apply_color))


# ======================================================================
# 内部辅助函数
# ======================================================================
def _safe_configure(widget, **kwargs):
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


def _make_dim_apply(widget, prop: str):
    """生成 dimension 快速应用函数"""
    def _apply(w, value):
        _safe_configure(w, **{prop: int(round(value))})
    return _apply


def _set_btn_fg_fast(btn, color: str):
    """通过 canvas 直接设置按钮填充颜色（绕过 _draw）"""
    try:
        canvas = btn._canvas
        canvas.itemconfig("inner_parts", fill=color)
        # 同步文字标签背景
        tl = getattr(btn, "_text_label", None)
        if tl is not None:
            tl.configure(bg=color)
        # 同步内部状态
        btn._fg_color = color
    except Exception:
        pass


def _set_border_color_fast(widget, color: str):
    """通过 canvas 直接设置边框颜色"""
    try:
        canvas = widget._canvas
        canvas.itemconfig("border_parts", fill=color, outline=color)
        if hasattr(widget, "_border_color"):
            widget._border_color = color
    except Exception:
        pass


def _animate_border_color_fast(widget, animator, from_color, to_color, duration):
    """用调度器动画边框颜色（快速路径）"""
    animator.animate(
        widget, "border_color_anim",
        from_color, to_color,
        duration, Easing.ease_out_cubic,
        apply_fn=lambda w, c: _set_border_color_fast(w, c),
    )


def _flash_color(btn, animator, orig_fg):
    """按钮点击时的颜色闪烁（浅色闪烁，不破坏原色）"""
    # 根据按钮类型选择闪烁色：品牌色按钮用浅绿，浅色按钮用浅灰
    r, g, b = ColorUtils.parse_hex(orig_fg)
    brightness = (r + g + b) / 3
    if brightness > 180:
        # 浅色按钮：闪到更浅的灰色
        flash_color = "#E5E7EB"
    else:
        # 深色/品牌色按钮：闪到浅绿色
        flash_color = TD_BRAND_LIGHT

    def _apply(widget, color):
        _set_btn_fg_fast(widget, color)

    def _restore(widget, color):
        """动画结束后强制还原颜色"""
        _set_btn_fg_fast(widget, color)
        try:
            widget.configure(fg_color=color)
        except Exception:
            pass

    # 快速变浅色 → 弹簧回原色
    animator.animate(btn, "fg_flash", orig_fg, flash_color,
                     int(JellyEffects.JELLY_DURATION * 0.12),
                     Easing.ease_in_cubic,
                     apply_fn=_apply,
                     on_complete=lambda: animator.animate(
                         btn, "fg_flash", flash_color, orig_fg,
                         int(JellyEffects.JELLY_DURATION * 0.88),
                         Easing.spring,
                         apply_fn=_apply,
                         on_complete=lambda: _restore(btn, orig_fg)))
