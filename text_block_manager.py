#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
مدير الكتل النصية لمعالجة كتب الشطرنج PDF
النسخة: 2.0.0
التاريخ: 2025-01-26 11:24:26
المؤلف: x9ci
"""

import re
import os
import sys
import logging
import json
from typing import Dict, List, Tuple
from datetime import datetime
try:
    from langdetect import detect
except ImportError:
    detect = lambda x: 'en' if x.isascii() else 'ar'



# ثوابت عامة
VERSION = '2.0.0'
AUTHOR = 'x9ci'
CURRENT_DATE = '2025-01-26 11:24:26'

# ثوابت المعالجة
DEFAULT_CONFIG = {
    'x_tolerance': 2,
    'y_tolerance': 3,
    'merge_distance': 20,
    'min_block_size': 2,
    'max_cache_size': 1000,
    'supported_languages': ['ar', 'en'],
    'debug_mode': False
}

# أنماط الشطرنج
CHESS_PATTERNS = {
    'piece_moves': r'\b([KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b',
    'pawn_moves': r'\b([a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?)\b',
    'castling': r'\b(O-O(?:-O)?)[+#]?\b',
    'move_numbers': r'^\d+\.(?:\.\.)?',
    'evaluation': r'[±∓⩲⩱∞=⟳↑↓⇆]{1,2}|[+\-](?:\d+\.?\d*|\.\d+)',
    'annotation': r'(?:!!|\?\?|!|\?|!?!|!\?|⊕|⩱|⩲)',
    'result': r'\b(?:1-0|0-1|½-½|1/2-1/2)\b',
    'squares': r'\b[a-h][1-8]\b',
    'piece_symbols': r'[♔♕♖♗♘♙♚♛♜♝♞♟]',
    'variations': r'\([^\)]+\)',
    'comments': r'\{[^}]*\}'
}


class TextBlockManager:
    """مدير الكتل النصية المتخصص في معالجة كتب الشطرنج مع دعم كامل للغة العربية"""
    
    def __init__(self, config_manager=None):
        """
        تهيئة مدير الكتل النصية
        
        Args:
            config_manager: مدير التكوين (اختياري)
        """
        # تهيئة السجل
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # تكوين المعالج
        self.config = self._init_config(config_manager)
        
        # تهيئة المتغيرات الداخلية
        self.stats = self._init_stats()
        self.current_page = 0
        self._cached_blocks = {}
        self.chess_patterns = self._compile_chess_patterns()
        self.language_detector = self._init_language_detector()
        
        # تسجيل بدء التشغيل
        self.logger.info(f"تم تهيئة TextBlockManager v{VERSION} ({CURRENT_DATE})")

    def _setup_logging(self):
        """إعداد نظام التسجيل"""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _init_config(self, config_manager) -> Dict:
        """تهيئة التكوين"""
        config = DEFAULT_CONFIG.copy()
        if config_manager:
            config.update(config_manager.get('text_block_manager', {}))
        return config

    def _init_stats(self) -> Dict:
        """تهيئة الإحصائيات"""
        return {
            'start_time': CURRENT_DATE,
            'total_blocks': 0,
            'chess_blocks': 0,
            'text_blocks': 0,
            'merged_blocks': 0,
            'arabic_blocks': 0,
            'english_blocks': 0,
            'processed_blocks': 0,
            'failed_blocks': 0,
            'pages_processed': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }

    def _compile_chess_patterns(self) -> Dict:
        """تجميع أنماط الشطرنج"""
        return {
            name: re.compile(pattern)
            for name, pattern in CHESS_PATTERNS.items()
        }

    def _init_language_detector(self):
        """تهيئة كاشف اللغة"""
        try:
            from langdetect import detect
            return detect
        except ImportError:
            self.logger.warning(
                "لم يتم العثور على مكتبة langdetect. سيتم استخدام الكشف البسيط."
            )
            return lambda x: 'en' if x.isascii() else 'ar'
        
    def process_page_content(self, page_data) -> List[Dict]:
        """
        معالجة محتوى الصفحة واستخراج الكتل
        
        Args:
            page_data: صفحة PDF من pdfplumber
            
        Returns:
            List[Dict]: قائمة من الكتل المعالجة
        """
        try:
            # التحقق من صحة البيانات
            self._validate_page_data(page_data)
            
            # تحديث المعلومات
            self.current_page += 1
            self.stats['pages_processed'] += 1
            self.logger.info(f"معالجة الصفحة {self.current_page}")

            # 1. استخراج النص والكلمات
            words = self._extract_words(page_data)
            if not words:
                self.logger.warning(f"لم يتم العثور على نص في الصفحة {self.current_page}")
                return []

            # 2. معالجة الكلمات وإنشاء الكتل
            blocks = self._process_words_to_blocks(words)
            
            # 3. تحليل وتصنيف الكتل
            analyzed_blocks = self._analyze_blocks(blocks)
            
            # 4. تحديث الإحصائيات
            self._update_stats(analyzed_blocks)
            
            return analyzed_blocks

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الصفحة {self.current_page}: {str(e)}")
            self.stats['failed_blocks'] += 1
            return []

    def _extract_words(self, page_data) -> List[Dict]:
        """
        استخراج الكلمات من الصفحة مع تحسين الدقة
        """
        try:
            # استخراج النص مع خيارات متقدمة
            words = page_data.extract_words(
                keep_blank_chars=True,
                extra_attrs=['fontname', 'size', 'strokewidth', 'fill'],
                x_tolerance=self.config['x_tolerance'],
                y_tolerance=self.config['y_tolerance'],
                split_at_punctuation=False  # لتحسين استخراج حركات الشطرنج
            )
            
            # معالجة وتنظيف الكلمات
            cleaned_words = []
            for word in words:
                if not word['text'].strip():
                    continue
                    
                # تنظيف وتحسين النص
                cleaned_text = self._clean_text(word['text'])
                if not cleaned_text:
                    continue
                    
                # إضافة معلومات إضافية
                word.update({
                    'text': cleaned_text,
                    'language': self._detect_text_language(cleaned_text),
                    'is_chess': bool(any(p.search(cleaned_text) for p in self.chess_patterns.values())),
                    'processing_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                })
                
                cleaned_words.append(word)
                
            self.logger.debug(f"تم استخراج {len(cleaned_words)} كلمة من الصفحة {self.current_page}")
            return cleaned_words

        except Exception as e:
            self.logger.error(f"خطأ في استخراج الكلمات: {str(e)}")
            return []

    def _process_words_to_blocks(self, words: List[Dict]) -> List[Dict]:
        """
        تحويل الكلمات إلى كتل مع تحسين الدقة
        """
        try:
            # 1. ترتيب الكلمات حسب الموقع
            sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
            
            # 2. تجميع الكلمات في سطور
            lines = self._group_words_to_lines(sorted_words)
            
            # 3. تجميع السطور في كتل
            raw_blocks = self._group_lines_to_blocks(lines)
            
            # 4. دمج الكتل المتقاربة
            merged_blocks = self._merge_related_blocks(raw_blocks)
            
            return merged_blocks

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الكلمات: {str(e)}")
            return []

    def _group_words_to_lines(self, words: List[Dict]) -> List[List[Dict]]:
        """
        تجميع الكلمات في سطور
        """
        lines = []
        current_line = []
        current_y = None

        for word in words:
            if current_y is None:
                current_y = word['top']
                current_line = [word]
            elif abs(word['top'] - current_y) <= self.config['y_tolerance']:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(sorted(current_line, key=lambda w: w['x0']))
                current_line = [word]
                current_y = word['top']

        if current_line:
            lines.append(sorted(current_line, key=lambda w: w['x0']))

        return lines

    def _group_lines_to_blocks(self, lines: List[List[Dict]]) -> List[Dict]:
        """
        تجميع السطور في كتل
        """
        blocks = []
        current_block_lines = []
        current_block_y = None

        for line in lines:
            if not line:
                continue

            if current_block_y is None:
                current_block_y = line[0]['top']
                current_block_lines = [line]
            elif abs(line[0]['top'] - current_block_y) <= self.config['merge_distance']:
                current_block_lines.append(line)
            else:
                if current_block_lines:
                    block = self._create_block_from_lines(current_block_lines)
                    if block:
                        blocks.append(block)
                current_block_lines = [line]
                current_block_y = line[0]['top']

        if current_block_lines:
            block = self._create_block_from_lines(current_block_lines)
            if block:
                blocks.append(block)

        return blocks
    
    def _clean_text(self, text: str) -> str:
        """
        تنظيف وتحسين النص
        """
        try:
            # إزالة المسافات الزائدة
            text = ' '.join(text.split())
            
            # تنظيف الأحرف الخاصة
            text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
            
            # تحسين علامات الشطرنج
            text = text.replace('0-0', 'O-O')  # تصحيح التحصين
            text = text.replace('0-0-0', 'O-O-O')
            
            return text.strip()
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف النص: {str(e)}")
            return text

    def _create_block_from_lines(self, lines: List[List[Dict]]) -> Dict:
        """
        إنشاء كتلة من مجموعة سطور
        """
        try:
            all_words = [word for line in lines for word in line]
            if not all_words:
                return None

            # تجميع النص
            text = ' '.join(
                ' '.join(w['text'] for w in line)
                for line in lines
            )

            # حساب الإطار المحيط
            bbox = self._calculate_bbox(all_words)
            
            # إنشاء معرف فريد للكتلة
            block_id = f"block_{self.current_page}_{len(self._cached_blocks)}_{datetime.utcnow().strftime('%H%M%S')}"

            # إنشاء الكتلة
            block = {
                'block_id': block_id,
                'text': text,
                'bbox': bbox,
                'font': all_words[0].get('fontname', ''),
                'size': all_words[0].get('size', 0),
                'language': self._get_dominant_language(all_words),
                'page_number': self.current_page,
                'words': all_words,
                'lines': lines,
                'metadata': {
                    'word_count': len(all_words),
                    'line_count': len(lines),
                    'creation_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_chess': any(w.get('is_chess', False) for w in all_words)
                }
            }

            # تخزين في الذاكرة المؤقتة
            self._add_to_cache(block_id, block)

            return block

        except Exception as e:
            self.logger.error(f"خطأ في إنشاء الكتلة: {str(e)}")
            return None