"""
OCR 引擎模块 — 基于 PaddleOCR 实现体检报告文字提取
支持图片 (jpg/png/bmp) 和 PDF 两种输入
首次运行时 PaddleOCR 会自动下载模型（约10MB）
"""

from __future__ import annotations

import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class OCREngine:
    """PaddleOCR 封装，提供图片和 PDF 文字提取能力"""

    def __init__(self, use_gpu: bool = False):
        """
        初始化 OCR 引擎

        Args:
            use_gpu: 是否使用 GPU 加速（需要安装 paddlepaddle-gpu）
        """
        self._ocr = None
        self._use_gpu = use_gpu
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """懒加载 PaddleOCR 实例，避免 import 时即下载模型"""
        if self._initialized:
            return

        try:
            from paddleocr import PaddleOCR

            logger.info("正在初始化 PaddleOCR（首次运行会自动下载模型）...")
            # PaddleOCR 3.x API: use_textline_orientation, lang, device
            # PaddleOCR 2.x API: use_angle_cls, lang, use_gpu, show_log
            import inspect
            init_params = inspect.signature(PaddleOCR.__init__).parameters
            kwargs = {"lang": "ch"}
            if "use_textline_orientation" in init_params:
                # PaddleOCR 3.x
                kwargs["use_textline_orientation"] = True
                # PaddlePaddle 3.x oneDNN has a bug on Windows, disable it
                import os as _os
                _os.environ.setdefault("FLAGS_use_mkldnn", "0")
            else:
                # PaddleOCR 2.x
                kwargs["use_angle_cls"] = True
                kwargs["use_gpu"] = self._use_gpu
                kwargs["show_log"] = False
            self._ocr = PaddleOCR(**kwargs)
            self._initialized = True
            logger.info("PaddleOCR 初始化完成")
        except ImportError:
            logger.error(
                "PaddleOCR 未安装，请执行: pip install paddleocr paddlepaddle"
            )
            raise
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise

    # ------------------------------------------------------------------
    #  图片 OCR
    # ------------------------------------------------------------------

    def extract_text_from_image(self, image_path: str) -> List[str]:
        """
        从图片中提取文字

        Args:
            image_path: 图片文件路径（支持 jpg/png/bmp 等）

        Returns:
            提取出的文本行列表，每行一个字符串
        """
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        self._ensure_initialized()

        try:
            result = self._ocr.ocr(image_path)
            lines: List[str] = []

            if not result:
                logger.warning(f"OCR 未识别到任何文字: {image_path}")
                return lines

            # PaddleOCR 返回格式兼容:
            # 2.x: [[ [box, (text, confidence)], ... ]]
            # 3.x: [OCRResult(json={'res': {'rec_texts': [...], 'rec_scores': [...]}}), ...]
            for page in result:
                if page is None:
                    continue
                # 3.x: page may be an OCRResult object with .json attribute
                if hasattr(page, "json"):
                    res = page.json
                    if isinstance(res, dict) and "res" in res:
                        res = res["res"]
                    texts = res.get("rec_texts", []) if isinstance(res, dict) else []
                    scores = res.get("rec_scores", []) if isinstance(res, dict) else []
                    for i, text in enumerate(texts):
                        conf = scores[i] if i < len(scores) else 1.0
                        if conf > 0.5:
                            lines.append(str(text).strip())
                elif isinstance(page, list):
                    # 2.x format
                    for line_info in page:
                        if line_info and len(line_info) >= 2:
                            text = line_info[1][0]
                            confidence = line_info[1][1]
                            if confidence > 0.5:
                                lines.append(text.strip())

            logger.info(f"OCR 完成: {image_path} -> {len(lines)} 行文字")
            return lines

        except Exception as e:
            logger.error(f"图片 OCR 失败 ({image_path}): {e}")
            raise

    # ------------------------------------------------------------------
    #  PDF OCR
    # ------------------------------------------------------------------

    def extract_text_from_pdf(self, pdf_path: str) -> List[str]:
        """
        从 PDF 中提取文字（逐页转图片后 OCR）

        Args:
            pdf_path: PDF 文件路径

        Returns:
            提取出的文本行列表，每行一个字符串
        """
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        self._ensure_initialized()

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            all_lines: List[str] = []

            logger.info(f"开始处理 PDF: {pdf_path} ({doc.page_count} 页)")

            for page_num in range(doc.page_count):
                page = doc[page_num]

                # 先尝试直接提取文本层（数字原生 PDF）
                text = page.get_text("text")
                if text and text.strip():
                    logger.info(
                        f"第 {page_num + 1} 页: 提取到文本层，"
                        f"共 {len(text.strip().splitlines())} 行"
                    )
                    all_lines.extend(
                        line.strip()
                        for line in text.strip().splitlines()
                        if line.strip()
                    )
                    continue

                # 无文本层，转为图片后 OCR
                logger.info(f"第 {page_num + 1} 页: 无文本层，转图片 OCR")
                zoom = 2.0  # 提高分辨率以增强 OCR 精度
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # 保存为临时图片
                import tempfile

                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as tmp_img:
                    tmp_path = tmp_img.name
                    pix.save(tmp_path)

                try:
                    page_lines = self.extract_text_from_image(tmp_path)
                    all_lines.extend(page_lines)
                finally:
                    os.unlink(tmp_path)

            doc.close()
            logger.info(f"PDF OCR 完成: {pdf_path} -> {len(all_lines)} 行文字")
            return all_lines

        except ImportError:
            logger.error("PyMuPDF 未安装，请执行: pip install PyMuPDF")
            raise
        except Exception as e:
            logger.error(f"PDF OCR 失败 ({pdf_path}): {e}")
            raise

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    def extract_text(self, file_path: str) -> List[str]:
        """
        自动判断文件类型并提取文字

        Args:
            file_path: 文件路径（图片或 PDF）

        Returns:
            提取出的文本行列表
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return self.extract_text_from_pdf(file_path)
        elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
            return self.extract_text_from_image(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
