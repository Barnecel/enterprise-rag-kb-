# -*- coding: utf-8 -*-
"""
视觉图片描述模块 (Vision Captioner)
使用 oMLX 现有多模态 chat 模型（Qwen3.5-9B，架构支持图片输入）为无文字图片生成中文描述。
- 惰性探测：首次调用时用最小 1x1 图片验证模型支持 image_url
- 失败降级：探测失败或调用异常均返回空串，不阻塞入库
"""
import base64
import io
import threading

from utils.config_handler import config
from utils.logger_handler import logger

LLM_CONFIG = config.get_section('llm')

# 1x1 透明 PNG（用于探测模型是否支持图片输入）
_MIN_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)

_IMAGE_CONTENT_TYPES = ('image/png', 'image/jpeg', 'image/jpg', 'image/webp')


class VisionCaptioner:
    def __init__(self):
        self._api_base = LLM_CONFIG.get('api_base', 'http://127.0.0.1:8000/v1')
        self._api_key = LLM_CONFIG.get('api_key', '')
        self._model = LLM_CONFIG.get('model_name', '')
        self._lock = threading.Lock()
        self._tested = False
        self.available = False

    def _check(self) -> bool:
        """探测当前 chat 模型是否支持图片输入（只做一次）"""
        if self._tested:
            return self.available
        with self._lock:
            if self._tested:
                return self.available
            self._tested = True
            try:
                import requests
                b64 = base64.b64encode(_MIN_PNG).decode()
                data = {
                    'model': self._model,
                    'messages': [{'role': 'user', 'content': [
                        {'type': 'text', 'text': '回复OK'},
                        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}}
                    ]}],
                    'max_tokens': 5,
                }
                r = requests.post(f'{self._api_base}/chat/completions',
                                  headers={'Authorization': f'Bearer {self._api_key}',
                                           'Content-Type': 'application/json'},
                                  json=data, timeout=30)
                self.available = (r.status_code == 200)
                if self.available:
                    logger.info(f"Vision caption available (model {self._model})")
                else:
                    logger.warning(f"Vision caption unavailable: HTTP {r.status_code}")
            except Exception as e:
                self.available = False
                logger.warning(f"Vision caption check failed: {e}")
        return self.available

    @staticmethod
    def _to_png_bytes(image_bytes: bytes) -> bytes:
        """把任意 PIL 可读格式转成 PNG 字节（防 WMF/EMF 等不支持格式）"""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
        except Exception:
            return image_bytes

    def caption(self, image_bytes: bytes) -> str:
        """生成中文图片描述；失败返回空串"""
        if not self._check():
            return ''
        try:
            import requests
            png = self._to_png_bytes(image_bytes)
            b64 = base64.b64encode(png).decode()
            data = {
                'model': self._model,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'text', 'text': '用中文简要描述这张图片的内容和主题，不超过50字。只输出描述本身。'},
                    {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}}
                ]}],
                'temperature': 0.3,
                'max_tokens': 200,
            }
            r = requests.post(f'{self._api_base}/chat/completions',
                              headers={'Authorization': f'Bearer {self._api_key}',
                                       'Content-Type': 'application/json'},
                              json=data, timeout=60)
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content'].strip()
                return content
            logger.warning(f"Vision caption HTTP {r.status_code}")
            return ''
        except Exception as e:
            logger.warning(f"Vision caption failed: {e}")
            return ''


_captioner = None
_caption_lock = threading.Lock()


def caption_image(image_bytes: bytes) -> str:
    """模块级入口：对图片生成中文描述，失败返回空串"""
    global _captioner
    if _captioner is None:
        with _caption_lock:
            if _captioner is None:
                _captioner = VisionCaptioner()
    return _captioner.caption(image_bytes)
