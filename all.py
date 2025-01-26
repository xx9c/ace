#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF Translation Script
Created: 2025-01-23 19:26:20
Author: x9ci
Version: 2.0.0

This script handles PDF translation with Arabic text support.
"""

from reportlab.lib.pagesizes import letter, A4
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from googletrans import Translator
import re
import logging
from PIL import Image, ImageFont, ImageDraw, ImageEnhance, ImageFilter
import os
from pathlib import Path
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Union, Tuple, Any, Set
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO
import arabic_reshaper
from bidi.algorithm import get_display
import sys
import time
import json
from tqdm import tqdm
import urllib.request
import logging.handlers
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import hashlib
import atexit
from collections import defaultdict
import subprocess
from typing import Dict, List, Optional, Tuple
import argparse
from dataclasses import dataclass
import gc
import warnings
from text_block_manager import TextBlockManager  # استيراد TextBlockManager

# تجاهل تحذيرات الخطوط غير الضرورية
warnings.filterwarnings('ignore', category=UserWarning, 
                       message='.*Can\'t open file "(Helvetica|Times-Roman|Times-Bold)".*')

# ثوابت خاصة بالشطرنج
CHESS_NOTATIONS = {
    'algebraic': r'[a-h][1-8]',
    'descriptive': r'[KQRBN][a-h][1-8]',
    'pgn': r'\d+\.'
}

# أنماط تدوين الشطرنج
MOVE_PATTERNS = {
    'castling': r'(O-O|O-O-O)',
    'captures': r'x',
    'check': r'\+',
    'mate': r'#'
}

# === تهيئة النظام والثوابت ===
SYSTEM_CONFIG = {
    'creation_date': '2025-01-24 16:56:48',
    'user': 'x9ci',
    'version': '2.0.0',
    'base_dir': '/home/dc/Public/pdftopdf/pdftran'
}




class ConfigManager:
    """إدارة الإعدادات والتكوين"""
    
    # الثوابت الافتراضية
    DEFAULT_VERSION = "2.0.0"
    DEFAULT_MEMORY_THRESHOLD = 1024  # بالميجابايت
    DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 ميجابايت
    
    def __init__(self):
        """تهيئة مدير الإعدادات"""
        self.version = self.DEFAULT_VERSION
        self.user = self._get_current_user()
        self.config_path = Path(__file__).parent / 'config.json'
        self.base_dir = Path(__file__).parent
        
        # إنشاء المجلدات الأساسية
        self.dirs = self._setup_directories()
        
        # تحميل الإعدادات
        self.config = self.load_config()
        
        # إعداد التسجيل
        self._setup_logging()

    def _get_current_user(self) -> str:
        """الحصول على اسم المستخدم الحالي"""
        try:
            import os
            return os.getenv('USER') or os.getenv('USERNAME') or 'unknown'
        except:
            return 'unknown'

    def _setup_directories(self) -> Dict[str, Path]:
        """إعداد المجلدات الأساسية"""
        dirs = {
            'root': self.base_dir / 'pdftran',
            'input': self.base_dir / 'pdftran/input',
            'output': self.base_dir / 'pdftran/output',
            'temp': self.base_dir / 'pdftran/temp',
            'logs': self.base_dir / 'pdftran/logs',
            'fonts': self.base_dir / 'fonts'
        }
        
        # إنشاء المجلدات
        for dir_path in dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
            
        return dirs
    
    def load_config(self) -> dict:
        """تحميل إعدادات التكوين"""
        default_config = {
            'version': self.DEFAULT_VERSION,
            'user': self.user,
            'memory_threshold': self.DEFAULT_MEMORY_THRESHOLD,
            'max_file_size': self.DEFAULT_MAX_FILE_SIZE,
            'font_paths': [
                str(self.dirs['fonts'] / 'Amiri-Regular.ttf'),
                '/usr/share/fonts/truetype/fonts-arabeyes/ae_AlArabiya.ttf',
                '/usr/share/fonts/truetype/fonts-arabeyes/ae_Furat.ttf'
            ],
            'font_urls': {
                'Amiri-Regular.ttf': 'https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf',
                'ae_AlArabiya.ttf': 'https://github.com/fonts-arabeyes/ae_fonts/raw/master/ae_fonts_1.1/Fonts/TrueType/ae_AlArabiya.ttf'
            },
            'tesseract_config': {
                'lang': 'ara+eng',
                'config': '--psm 3'
            },
            'translation': {
                'batch_size': 10,
                'timeout': 30,
                'retries': 3
            },
            'output': {
                'dpi': 300,
                'quality': 95,
                'format': 'PDF'
            },
            'processing': {
                'threads': 4,
                'chunk_size': 1000,
                'cache_enabled': True
            }
        }

        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    return {**default_config, **loaded_config}
            return default_config
        except Exception as e:
            logging.error(f"خطأ في تحميل ملف الإعدادات: {e}")
            return default_config

    def save_config(self) -> bool:
        """حفظ إعدادات التكوين"""
        try:
            # تحديث التاريخ والوقت
            self.config['last_updated'] = datetime.now().isoformat()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logging.error(f"خطأ في حفظ ملف الإعدادات: {e}")
            return False
        

    def _setup_logging(self):
        """إعداد نظام التسجيل"""
        log_file = self.dirs['logs'] / f"config_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def get(self, key: str, default: Any = None) -> Any:
        """الحصول على قيمة إعداد معين"""
        return self.config.get(key, default)

    def update(self, key: str, value: Any) -> bool:
        """تحديث قيمة إعداد معين"""
        try:
            self.config[key] = value
            return self.save_config()
        except Exception as e:
            logging.error(f"خطأ في تحديث الإعدادات: {e}")
            return False

    def get_settings_dict(self) -> dict:
        """الحصول على نسخة من الإعدادات الحالية"""
        return self.config.copy()

    def validate_config(self) -> List[str]:
        """التحقق من صحة الإعدادات"""
        errors = []
        
        # التحقق من المجلدات
        for dir_name, dir_path in self.dirs.items():
            if not dir_path.exists():
                errors.append(f"المجلد {dir_name} غير موجود: {dir_path}")

        # التحقق من الخطوط
        for font_path in self.config['font_paths']:
            if not Path(font_path).exists():
                errors.append(f"ملف الخط غير موجود: {font_path}")

        # التحقق من القيم الرقمية
        if self.config['memory_threshold'] <= 0:
            errors.append("قيمة memory_threshold يجب أن تكون أكبر من صفر")
        
        if self.config['max_file_size'] <= 0:
            errors.append("قيمة max_file_size يجب أن تكون أكبر من صفر")

        return errors

    @property
    def memory_threshold(self) -> int:
        """الحصول على حد الذاكرة"""
        return self.config.get('memory_threshold', self.DEFAULT_MEMORY_THRESHOLD)

    @property
    def max_file_size(self) -> int:
        """الحصول على الحد الأقصى لحجم الملف"""
        return self.config.get('max_file_size', self.DEFAULT_MAX_FILE_SIZE)
        

class CacheManager:
    """إدارة التخزين المؤقت للترجمات"""
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent / 'cache'
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / 'translations.json'
        self.cache = self.load_cache()
        self.lock = threading.Lock()

    def load_cache(self) -> Dict[str, str]:
        """تحميل الترجمات المخزنة مؤقتاً"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"خطأ في تحميل الذاكرة المؤقتة: {e}")
            return {}

    def save_cache(self) -> bool:
        """حفظ الترجمات في الذاكرة المؤقتة"""
        try:
            with self.lock:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logging.error(f"خطأ في حفظ الذاكرة المؤقتة: {e}")
            return False

    def get_translation(self, text: str) -> Optional[str]:
        """الحصول على ترجمة مخزنة"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return self.cache.get(text_hash)

    def store_translation(self, text: str, translation: str) -> bool:
        """تخزين ترجمة جديدة"""
        try:
            with self.lock:
                text_hash = hashlib.md5(text.encode()).hexdigest()
                self.cache[text_hash] = translation
                return self.save_cache()
        except Exception as e:
            logging.error(f"خطأ في تخزين الترجمة: {e}")
            return False

    def clear_cache(self) -> bool:
        """مسح الذاكرة المؤقتة"""
        try:
            with self.lock:
                self.cache = {}
                return self.save_cache()
        except Exception as e:
            logging.error(f"خطأ في مسح الذاكرة المؤقتة: {e}")
            return False   
        

class FontManager:
    """إدارة الخطوط وتحميلها"""
    
    def __init__(self, config_manager: ConfigManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.font_name: str = "ArabicFont"
        self.loaded_fonts: List[str] = []
        self.base_path = Path(__file__).parent
        self.fonts_dir = self.base_path / "fonts"
        self.fonts_dir.mkdir(exist_ok=True)
        self._setup_fonts()

    def _setup_fonts(self) -> None:
        """إعداد وتهيئة الخطوط الأولية"""
        self.font_paths = self.config.get('font_paths', [])
        self.font_urls = self.config.get('font_urls', {})
        self.register_default_fonts()

    def register_default_fonts(self) -> None:
        """تسجيل الخطوط الافتراضية"""
        default_fonts = [
            ('Helvetica', 'Helvetica'),
            ('Helvetica-Bold', 'Helvetica-Bold'),
            ('Times-Roman', 'Times-Roman'),
            ('Times-Bold', 'Times-Bold')
        ]
        for font_name, font_path in default_fonts:
            if font_name not in pdfmetrics.getRegisteredFontNames():
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                except Exception as e:
                    self.logger.warning(f"فشل تسجيل الخط {font_name}: {e}")

    def check_font_paths(self) -> List[str]:
        """التحقق من مسارات الخطوط المتوفرة"""
        possible_font_dirs = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / "Library/Fonts",  # MacOS
            Path("C:\\Windows\\Fonts"),  # Windows
            self.fonts_dir
        ]
        
        found_fonts: List[str] = []
        arab_keywords = ['arab', 'amiri', 'noto', 'freesans']
        
        self.logger.info("جاري البحث عن الخطوط المتوفرة...")
        for font_dir in possible_font_dirs:
            if font_dir.exists():
                self.logger.info(f"البحث في المجلد: {font_dir}")
                for font_path in font_dir.rglob("*.[to][tt][ff]"):
                    if any(kw in font_path.name.lower() for kw in arab_keywords):
                        found_fonts.append(str(font_path))
                        self.logger.info(f"تم العثور على خط: {font_path}")
        
        return found_fonts

    def download_font(self, font_name: str, url: str) -> bool:
        """تحميل خط من الإنترنت"""
        try:
            font_path = self.fonts_dir / font_name
            self.logger.info(f"جاري تحميل الخط {font_name}...")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            progress_bar = tqdm(
                total=total_size,
                unit='iB',
                unit_scale=True,
                desc=f"تحميل {font_name}"
            )
            
            with open(font_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    progress_bar.update(len(data))
                    f.write(data)
            
            progress_bar.close()
            self.logger.info(f"تم تحميل الخط بنجاح: {font_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"خطأ في تحميل الخط {font_name}: {e}")
            return False

    def load_font(self, font_path: str) -> bool:
        """تحميل خط معين"""
        try:
            font_name = f"Arabic_{Path(font_path).stem}"
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                self.loaded_fonts.append(font_path)
                self.logger.info(f"تم تحميل الخط: {font_path}")
                return True
            return True
        except Exception as e:
            self.logger.warning(f"فشل تحميل الخط {font_path}: {str(e)}")
            return False

    def initialize_fonts(self) -> bool:
        """تهيئة الخطوط العربية"""
        try:
            # محاولة تحميل الخطوط المحلية
            for font_path in self.font_paths:
                if Path(font_path).exists():
                    if self.load_font(font_path):
                        return True

            # محاولة تحميل الخطوط من الإنترنت إذا لم تتوفر محلياً
            if not self.loaded_fonts:
                self.logger.warning("لم يتم العثور على خطوط محلية. جاري التحميل من الإنترنت...")
                for font_name, url in self.font_urls.items():
                    if self.download_font(font_name, url):
                        font_path = self.fonts_dir / font_name
                        if self.load_font(str(font_path)):
                            return True

            return bool(self.loaded_fonts)

        except Exception as e:
            self.logger.error(f"خطأ في تهيئة الخطوط: {str(e)}")
            return False

    def get_arabic_font(self) -> Optional[str]:
        """الحصول على مسار الخط العربي المحمل"""
        return next(iter(self.loaded_fonts), None)


class ResourceManager:
    def __init__(self):
        self._resources = {}
        self._locks = {}

    def get_processor(self, resource_id: str):
        """الحصول على معالج للمورد"""
        if resource_id not in self._resources:
            self._resources[resource_id] = PDFProcessor()
            self._locks[resource_id] = False
        return self._resources[resource_id]

    def is_processing(self, resource_id: str) -> bool:
        """التحقق من حالة المعالجة"""
        return self._locks.get(resource_id, False)

    def set_processing(self, resource_id: str, state: bool):
        """تعيين حالة المعالجة"""
        self._locks[resource_id] = state


class ArabicTextHandler:
    """معالجة النصوص العربية والخطوط"""
    def __init__(self):
        self.font_size = 12
        self.font_name = 'Arabic'  # إضافة متغير font_name
        self.initialize_fonts()

    def initialize_fonts(self):
        """تهيئة الخطوط العربية"""
        try:
            # تجنب إعادة تحميل الخطوط إذا كانت مسجلة مسبقاً
            if self.font_name in pdfmetrics.getRegisteredFontNames():
                logging.debug(f"الخط {self.font_name} مسجل مسبقاً")
                return True

            current_dir = Path(__file__).parent
            fonts_dir = current_dir / "fonts"
            fonts_dir.mkdir(exist_ok=True)

            # تجاهل تحذيرات الخطوط الافتراضية
            import warnings
            warnings.filterwarnings('ignore', category=UserWarning, 
                                  message='.*Can\'t open file "(Helvetica|Times-Roman|Times-Bold)".*')

            # قائمة الخطوط العربية
            arabic_fonts = [
                # الخطوط المحلية أولاً
                fonts_dir / "Amiri-Regular.ttf",
                fonts_dir / "ae_AlArabiya.ttf",
                
                # خطوط النظام
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_AlArabiya.ttf"),
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_Furat.ttf"),
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_Khalid.ttf"),
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_Salem.ttf"),
                
                # خطوط احتياطية
                Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf")
            ]

            # محاولة تحميل خط عربي موجود
            for font_path in arabic_fonts:
                if font_path.exists():
                    try:
                        pdfmetrics.registerFont(TTFont(self.font_name, str(font_path)))
                        logging.info(f"تم تحميل الخط: {font_path}")
                        return True
                    except Exception as e:
                        logging.debug(f"فشل تحميل الخط {font_path}: {str(e)}")
                        continue

            # إذا لم يتم العثور على خط، حاول نسخ خط من النظام
            system_fonts = [
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_AlArabiya.ttf"),
                Path("/usr/share/fonts/truetype/fonts-arabeyes/ae_Furat.ttf")
            ]

            for system_font in system_fonts:
                if system_font.exists():
                    try:
                        dest_path = fonts_dir / system_font.name
                        if not dest_path.exists():  # تجنب النسخ إذا كان الملف موجوداً
                            shutil.copy2(str(system_font), str(dest_path))
                        pdfmetrics.registerFont(TTFont(self.font_name, str(dest_path)))
                        logging.info(f"تم نسخ وتحميل الخط: {dest_path}")
                        return True
                    except Exception as e:
                        logging.debug(f"فشل نسخ الخط {system_font}: {str(e)}")
                        continue

            # إذا لم يتم العثور على خط محلي، حاول التحميل من الإنترنت
            logging.info("لم يتم العثور على خط عربي محلي. جاري محاولة التحميل من الإنترنت...")
            return self.download_arabic_font()

        except Exception as e:
            logging.error(f"خطأ في تهيئة الخطوط: {e}")
            return False

    def download_arabic_font(self):
        """تحميل الخط العربي من الإنترنت"""
        try:
            font_urls = [
                "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
                "https://github.com/aerrami/arabic-fonts/raw/master/ae_AlArabiya.ttf"
            ]
            
            fonts_dir = Path(__file__).parent / "fonts"
            
            for font_url in font_urls:
                try:
                    font_name = Path(font_url).name
                    font_path = fonts_dir / font_name
                    
                    if font_path.exists():  # تجنب إعادة التحميل
                        logging.debug(f"الخط {font_name} موجود مسبقاً")
                        pdfmetrics.registerFont(TTFont(self.font_name, str(font_path)))
                        return True

                    logging.info(f"جاري محاولة تحميل الخط: {font_name}")
                    response = requests.get(font_url)
                    response.raise_for_status()
                    
                    with open(font_path, 'wb') as f:
                        f.write(response.content)
                    
                    pdfmetrics.registerFont(TTFont(self.font_name, str(font_path)))
                    logging.info(f"تم تحميل الخط {font_name} بنجاح")
                    return True
                    
                except Exception as e:
                    logging.debug(f"فشل تحميل الخط {font_name}: {str(e)}")
                    continue
            
            logging.error("فشل تحميل جميع الخطوط المتاحة")
            return False
                
        except Exception as e:
            logging.error(f"خطأ في تحميل الخط العربي: {e}")
            return False

    def process_arabic_text(self, text):
        """معالجة النص العربي"""
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except Exception as e:
            print(f"خطأ في معالجة النص العربي: {e}")
            return text

    def get_text_dimensions(self, text):
        """حساب أبعاد النص"""
        try:
            processed_text = self.process_arabic_text(text)
            width = len(processed_text) * self.font_size * 0.6
            height = self.font_size * 1.2
            return width, height
        except Exception as e:
            print(f"خطأ في حساب أبعاد النص: {e}")
            return 0, 0

class TextProcessor:
    def __init__(self):
        self.arabic_handler = None
        self.processed_blocks = 0
        self.translation_cache = {}
        self.total_chars = 0
        self.errors = []
        self.chess_stats = {
            'pieces_found': 0,
            'moves_found': 0,
            'diagrams_found': 0,
            'annotations_found': 0,
            'terms_found': 0,
            'variations_found': 0
        }
        
        # تهيئة الأنماط والقواميس
        self._init_chess_patterns()
        self._init_chess_pieces()
        self._init_chess_terms()
        self._init_nag_translations()

    def _init_chess_patterns(self):
        """تهيئة أنماط الشطرنج"""
        self.chess_patterns = {
            'moves': r'[KQRBN]?[a-h][1-8]',            # حركات القطع
            'captures': r'x',                           # الضرب
            'castling': r'O-O(?:-O)?',                 # التبييت
            'check': r'\+',                            # الشاه
            'mate': r'#',                              # الكش مات
            'pieces': r'[KQRBN]',                      # القطع
            'annotations': r'[!?]{1,2}',               # علامات التعليق
            'move_numbers': r'\d+\.',                  # أرقام النقلات
            'score': r'(?:1-0|0-1|1/2-1/2|\*)',       # نتيجة المباراة
            'nag': r'\$\d+',                          # رموز NAG
            'coordinates': r'[a-h][1-8]',              # إحداثيات المربعات
            'promotions': r'=[QRBN]',                  # الترقية
            'pin_symbols': r'†|‡',                     # رموز التثبيت
            'fork_symbols': r'⚔|∆',                    # رموز الشوكة
            'variation_start': r'\(',                  # بداية التنويع
            'variation_end': r'\)',                    # نهاية التنويع
            'comment_start': r'\{',                    # بداية التعليق
            'comment_end': r'\}',                      # نهاية التعليق
        }


    def _init_chess_pieces(self):
        """تهيئة قاموس القطع"""
        self.chess_pieces_ar = {
            # القطع الإنجليزية والعربية (كبيرة)
            'K': 'ملك',
            'Q': 'وزير',
            'R': 'طابية',
            'B': 'فيل',
            'N': 'حصان',
            'P': 'بيدق',
            # القطع الإنجليزية والعربية (صغيرة)
            'k': 'ملك',
            'q': 'وزير',
            'r': 'طابية',
            'b': 'فيل',
            'n': 'حصان',
            'p': 'بيدق',
        }
        
        # رموز القطع للمخططات
        self.diagram_symbols = {
            '♔': 'ملك أبيض',
            '♕': 'وزير أبيض',
            '♖': 'طابية بيضاء',
            '♗': 'فيل أبيض',
            '♘': 'حصان أبيض',
            '♙': 'بيدق أبيض',
            '♚': 'ملك أسود',
            '♛': 'وزير أسود',
            '♜': 'طابية سوداء',
            '♝': 'فيل أسود',
            '♞': 'حصان أسود',
            '♟': 'بيدق أسود',
        }

    def _init_chess_terms(self):
        """تهيئة قاموس المصطلحات الشطرنجية"""
        self.chess_terms = {
            # المصطلحات الأساسية
            'check': 'كش',
            'mate': 'مات',
            'stalemate': 'تعادل بالتجميد',
            'castle': 'تبييت',
            'promote': 'ترقية',
            'capture': 'ضرب',
            'en passant': 'أخذ في المرور',
            
            # المصطلحات التكتيكية
            'pin': 'تثبيت',
            'fork': 'شوكة',
            'skewer': 'سفود',
            'discovered attack': 'هجوم مكشوف',
            'double attack': 'هجوم مزدوج',
            'double check': 'كش مزدوج',
            'overloading': 'إرهاق القطعة',
            'deflection': 'إبعاد القطعة',
            'interference': 'تداخل',
            'zwischenzug': 'نقلة بينية',
            'zugzwang': 'إجبار على الحركة',
            
            # مصطلحات الافتتاح
            'opening': 'افتتاح',
            'development': 'تطوير',
            'center': 'مركز',
            'fianchetto': 'تطوير الفيل',
            'gambit': 'تضحية افتتاحية',
            'counter gambit': 'تضحية مضادة',
            
            # مصطلحات وسط اللعبة
            'middlegame': 'وسط اللعبة',
            'initiative': 'المبادرة',
            'attack': 'هجوم',
            'defense': 'دفاع',
            'counterplay': 'لعب مضاد',
            'prophylaxis': 'وقاية',
            
            # مصطلحات نهاية اللعبة
            'endgame': 'نهاية اللعبة',
            'passing pawn': 'بيدق متقدم',
            'outside passed pawn': 'بيدق متقدم خارجي',
            'protected passed pawn': 'بيدق متقدم محمي',
            'connected pawns': 'بيادق متصلة',
            'isolated pawn': 'بيدق معزول',
            'doubled pawns': 'بيادق مضاعفة',
            'backward pawn': 'بيدق متأخر',
            'majority': 'أغلبية بيادق',
            
            # مصطلحات التقييم
            'advantage': 'أفضلية',
            'winning advantage': 'أفضلية حاسمة',
            'slight advantage': 'أفضلية طفيفة',
            'equal': 'تعادل',
            'unclear': 'موقف غير واضح',
            'compensation': 'تعويض',
            'initiative': 'مبادرة',
            'counterplay': 'لعب مضاد',
        }

    
    def _init_nag_translations(self):
        """تهيئة ترجمات رموز NAG"""
        self.nag_translations = {
            # تقييم النقلات
            '$1': 'نقلة قوية',
            '$2': 'نقلة ضعيفة',
            '$3': 'نقلة ممتازة',
            '$4': 'خطأ فادح',
            '$5': 'نقلة مثيرة للتساؤل',
            '$6': 'نقلة مشكوك فيها',
            '$7': 'نقلة مجبرة',
            '$8': 'النقلة الوحيدة',
            '$9': 'أسوأ نقلة',
            '$10': 'موقف متعادل',
            '$11': 'موقف متكافئ',
            '$12': 'موقف معقد',
            '$13': 'موقف غامض',
            '$14': 'أفضلية طفيفة للأبيض',
            '$15': 'أفضلية طفيفة للأسود',
            '$16': 'أفضلية للأبيض',
            '$17': 'أفضلية للأسود',
            '$18': 'فوز للأبيض',
            '$19': 'فوز للأسود',
            '$20': 'أفضلية حاسمة للأبيض',
            '$21': 'أفضلية حاسمة للأسود',
            
            # تقييمات إضافية
            '$22': 'ضغط شديد',
            '$23': 'موقف حرج',
            '$24': 'مرونة أكبر',
            '$25': 'تنمية متأخرة',
            '$26': 'مبادرة',
            '$27': 'هجوم',
            '$28': 'تعويض عن المادة',
            '$29': 'تعويض عن الموقف',
            '$30': 'خط هجومي',
            '$31': 'خط دفاعي',
            '$32': 'ضغط على المركز',
            '$33': 'ضغط على الجناح',
            '$34': 'قيود موقعية',
            '$35': 'خط تطوير',
            '$36': 'خط مضاد'
        }

    def process_text(self, text: str) -> str:
        """معالجة النص المستخرج من PDF"""
        if not text:
            return None

        try:
            self.total_chars += len(text)
            blocks = self._split_into_blocks(text)
            
            processed_blocks = []
            for block in blocks:
                # التحقق من الذاكرة المؤقتة
                if block in self.translation_cache:
                    processed_block = self.translation_cache[block]
                else:
                    # معالجة الكتلة
                    processed_block = self._process_block(block)
                    if processed_block:
                        # معالجة مصطلحات الشطرنج
                        processed_block = self._process_chess_content(processed_block)
                        self.translation_cache[block] = processed_block

                if processed_block:
                    processed_blocks.append(processed_block)
                    self.processed_blocks += 1
                    
                    # تحديث الإحصائيات
                    self._update_chess_stats(processed_block)

            return '\n\n'.join(processed_blocks) if processed_blocks else None

        except Exception as e:
            self.errors.append(str(e))
            logging.error(f"خطأ في معالجة النص: {str(e)}")
            return None

    def _split_into_blocks(self, text: str) -> List[str]:
        """تقسيم النص إلى كتل"""
        try:
            # تقسيم بناءً على السطور الفارغة والمخططات
            blocks = []
            current_block = []
            lines = text.split('\n')
            
            for line in lines:
                if self._is_diagram_line(line):
                    # حفظ الكتلة السابقة إذا وجدت
                    if current_block:
                        blocks.append('\n'.join(current_block))
                        current_block = []
                    # إضافة سطر المخطط كتلة منفصلة
                    blocks.append(line)
                elif line.strip():
                    current_block.append(line)
                elif current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            
            # إضافة الكتلة الأخيرة إذا وجدت
            if current_block:
                blocks.append('\n'.join(current_block))
            
            return [block for block in blocks if block.strip()]

        except Exception as e:
            self.errors.append(f"خطأ في تقسيم النص: {str(e)}")
            return []
        

    def _process_chess_content(self, text: str) -> str:
        """معالجة محتوى الشطرنج في النص"""
        try:
            # معالجة المخططات
            if self._is_diagram_block(text):
                return self._process_chess_diagram(text)
            
            # معالجة النقلات والتعليقات
            text = self._process_chess_moves(text)
            text = self._process_chess_terms(text)
            text = self._process_chess_annotations(text)
            text = self._process_variations(text)
            
            return text

        except Exception as e:
            self.errors.append(f"خطأ في معالجة محتوى الشطرنج: {str(e)}")
            return text

    def _is_diagram_line(self, line: str) -> bool:
        """التحقق مما إذا كان السطر يمثل جزءاً من مخطط شطرنج"""
        # التحقق من وجود رموز قطع الشطرنج
        diagram_chars = set('♔♕♖♗♘♙♚♛♜♝♞♟.|-+')
        return any(char in diagram_chars for char in line)

    def _is_diagram_block(self, text: str) -> bool:
        """التحقق مما إذا كان النص يمثل مخطط شطرنج"""
        lines = text.split('\n')
        if len(lines) >= 8:
            diagram_lines = 0
            for line in lines:
                if self._is_diagram_line(line):
                    diagram_lines += 1
            return diagram_lines >= 8
        return False

    def _process_chess_diagram(self, text: str) -> str:
        """معالجة مخطط الشطرنج"""
        try:
            lines = text.split('\n')
            processed_lines = []
            
            # معالجة كل سطر في المخطط
            for line in lines:
                if self._is_diagram_line(line):
                    # استبدال رموز القطع بأسمائها العربية
                    for symbol, name in self.diagram_symbols.items():
                        line = line.replace(symbol, f"[{name}]")
                    self.chess_stats['diagrams_found'] += 1
                processed_lines.append(line)
            
            return '\n'.join(processed_lines)

        except Exception as e:
            self.errors.append(f"خطأ في معالجة مخطط الشطرنج: {str(e)}")
            return text

    def _process_chess_moves(self, text: str) -> str:
        """معالجة نقلات الشطرنج"""
        try:
            # معالجة التبييت
            text = re.sub(r'O-O-O', 'تبييت طويل', text)
            text = re.sub(r'O-O', 'تبييت قصير', text)
            
            # معالجة النقلات العادية
            for match in re.finditer(r'([KQRBN])?([a-h][1-8])', text):
                piece, square = match.groups()
                piece_name = self.chess_pieces_ar.get(piece, 'قطعة')
                text = text.replace(match.group(), f"{piece_name} إلى {square}")
                self.chess_stats['moves_found'] += 1
            
            # معالجة الضرب
            text = re.sub(r'x', 'يضرب', text)
            
            # معالجة الترقية
            text = re.sub(r'=([QRBN])', lambda m: f"يرقى إلى {self.chess_pieces_ar[m.group(1)]}", text)
            
            return text

        except Exception as e:
            self.errors.append(f"خطأ في معالجة نقلات الشطرنج: {str(e)}")
            return text

    def _process_chess_annotations(self, text: str) -> str:
        """معالجة تعليقات وعلامات الشطرنج"""
        try:
            # معالجة علامات التقييم
            annotations = {
                '!!': 'نقلة ممتازة',
                '!': 'نقلة جيدة',
                '??': 'خطأ فادح',
                '?': 'نقلة ضعيفة',
                '!?': 'نقلة مثيرة للاهتمام',
                '?!': 'نقلة مشكوك فيها'
            }
            
            for symbol, meaning in annotations.items():
                text = text.replace(symbol, f" ({meaning}) ")
                if symbol in text:
                    self.chess_stats['annotations_found'] += 1
            
            # معالجة رموز NAG
            for nag, translation in self.nag_translations.items():
                text = text.replace(nag, f" ({translation}) ")
            
            return text

        except Exception as e:
            self.errors.append(f"خطأ في معالجة تعليقات الشطرنج: {str(e)}")
            return text
        

    def _process_variations(self, text: str) -> str:
        """معالجة التنويعات في نقلات الشطرنج"""
        try:
            # تتبع مستوى التنويعات
            level = 0
            result = []
            buffer = ""
            
            for char in text:
                if char == '(':
                    if buffer:
                        result.append(buffer)
                        buffer = ""
                    level += 1
                    result.append(f"\nالتنويع {level}: ")
                    self.chess_stats['variations_found'] += 1
                elif char == ')':
                    if buffer:
                        result.append(buffer)
                        buffer = ""
                    level -= 1
                    result.append("\nنهاية التنويع\n")
                else:
                    buffer += char
                    
            if buffer:
                result.append(buffer)
                
            return ''.join(result)

        except Exception as e:
            self.errors.append(f"خطأ في معالجة التنويعات: {str(e)}")
            return text

    def _update_chess_stats(self, text: str) -> None:
        """تحديث إحصائيات الشطرنج"""
        try:
            # إحصاء القطع
            for piece in self.chess_pieces_ar.keys():
                self.chess_stats['pieces_found'] += text.count(piece)
            
            # إحصاء المصطلحات
            for term in self.chess_terms.values():
                self.chess_stats['terms_found'] += text.count(term)
            
        except Exception as e:
            self.errors.append(f"خطأ في تحديث الإحصائيات: {str(e)}")

    def get_stats(self) -> Dict[str, Union[int, List[str]]]:
        """الحصول على إحصائيات المعالجة"""
        return {
            'processed_blocks': self.processed_blocks,
            'total_chars': self.total_chars,
            'cached_blocks': len(self.translation_cache),
            'chess_statistics': self.chess_stats,
            'errors': self.errors
        }

    def reset_stats(self) -> None:
        """إعادة تعيين جميع الإحصائيات"""
        self.processed_blocks = 0
        self.total_chars = 0
        self.errors.clear()
        self.translation_cache.clear()
        self.chess_stats = {
            'pieces_found': 0,
            'moves_found': 0,
            'diagrams_found': 0,
            'annotations_found': 0,
            'terms_found': 0,
            'variations_found': 0
        }

    def _process_block(self, text: str) -> str:
        """معالجة كتلة نصية واحدة"""
        if not text:
            return None

        try:
            # إزالة الأسطر الفارغة المتتالية
            text = re.sub(r'\n\s*\n', '\n', text)
            
            # معالجة النص العربي
            if self.arabic_handler:
                text = self.arabic_handler.process(text)
            
            # تنظيف النص
            text = self._clean_text(text)
            
            # معالجة التنسيق
            text = self._format_text(text)
            
            # معالجة مصطلحات وتدوينات الشطرنج
            text = self._process_chess_terms(text)
            text = self._process_chess_notation(text)
            
            return text.strip() if text.strip() else None

        except Exception as e:
            self.errors.append(f"خطأ في معالجة الكتلة: {str(e)}")
            return None

    def _format_text(self, text: str) -> str:
        """تنسيق النص وتحسين مظهره"""
        if not text:
            return ""

        try:
            # إزالة المسافات الزائدة
            text = re.sub(r'\s+', ' ', text)
            
            # إزالة المسافات قبل علامات الترقيم
            text = re.sub(r'\s+([.,!?:;])', r'\1', text)
            
            # تصحيح المسافات بعد علامات الترقيم
            text = re.sub(r'([.,!?:;])(?!\s)', r'\1 ', text)
            
            # تصحيح علامات الاقتباس
            text = re.sub(r'(?<!["\'"])"(?!["\'""])', '\"', text)
            
            # تصحيح الأقواس
            text = re.sub(r'\(\s+', '(', text)
            text = re.sub(r'\s+\)', ')', text)
            
            return text.strip()

        except Exception as e:
            self.errors.append(f"خطأ في تنسيق النص: {str(e)}")
            return text

    def _clean_text(self, text: str) -> str:
        """تنظيف النص من الأخطاء الشائعة"""
        if not text:
            return ""

        try:
            # إزالة الأحرف الخاصة غير المرغوب فيها
            text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
            
            # توحيد نوع الأقواس
            text = text.replace('「', '"').replace('」', '"')
            text = text.replace('『', '"').replace('』', '"')
            
            # تصحيح الأرقام العربية
            arabic_numbers = {'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
                             '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'}
            for ar, en in arabic_numbers.items():
                text = text.replace(ar, en)
            
            return text.strip()

        except Exception as e:
            self.errors.append(f"خطأ في تنظيف النص: {str(e)}")
            return text
    
    
    def clear_cache(self) -> None:
        """مسح الذاكرة المؤقتة"""
        self.translation_cache.clear()

    def get_errors(self) -> List[str]:
        """الحصول على قائمة الأخطاء"""
        return self.errors

    def process_file(self, input_path: str, output_path: str) -> bool:
        """معالجة ملف PDF كامل"""
        try:
            # التحقق من وجود الملف
            if not Path(input_path).exists():
                raise FileNotFoundError(f"الملف غير موجود: {input_path}")

            # إعادة تعيين الإحصائيات
            self.reset_stats()
            
            # فتح وقراءة الملف
            with pdfplumber.open(input_path) as pdf:
                processed_pages = []
                
                # معالجة كل صفحة
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        processed_text = self.process_text(text)
                        if processed_text:
                            processed_pages.append(processed_text)

                # حفظ النتيجة
                if processed_pages:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write('\n\n'.join(processed_pages))
                    return True
                    
            return False

        except Exception as e:
            self.errors.append(f"خطأ في معالجة الملف: {str(e)}")
            logging.error(f"خطأ في معالجة الملف: {str(e)}")
            return False

    
class TextExtractor:
    """استخراج وتحليل النصوص من كتب الشطرنج PDF مع دعم متقدم للغة العربية"""
    
    def __init__(self, config_manager=None):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager or {}
        
        # تكوين المعالجة
        self.config_params = {
            'x_tolerance': 3,
            'y_tolerance': 3,
            'min_block_size': 2,
            'word_margin': 2,
            'char_margin': 2,
            'line_margin': 3
        }
        
        # تهيئة المكونات
        self.block_manager = None
        self.chess_patterns = self._init_chess_patterns()
        self.chess_keywords = self._init_chess_keywords()
        self.stats = self._init_stats()

    def _init_stats(self) -> Dict:
        """تهيئة الإحصائيات"""
        return {
            'total_pages': 0,
            'processed_pages': 0,
            'total_blocks': 0,
            'chess_blocks': 0,
            'text_blocks': 0,
            'diagrams': 0,
            'processing_errors': 0
        }

    def _init_chess_patterns(self) -> Dict:
        """تهيئة أنماط التعرف على عناصر الشطرنج"""
        return {
            'piece_moves': re.compile(r'\b([KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b'),
            'pawn_moves': re.compile(r'\b([a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?)\b'),
            'castling': re.compile(r'\b(O-O(?:-O)?)[+#]?\b'),
            'move_numbers': re.compile(r'^\d+\.(?:\.\.)?'),
            'evaluation': re.compile(r'[±∓⩲⩱∞=⟳↑↓⇆]{1,2}|[+\-](?:\d+\.?\d*|\.\d+)'),
            'annotation': re.compile(r'(?:!!|\?\?|!|\?|!?!|!\?|⊕|⩱|⩲)'),
            'result': re.compile(r'\b(?:1-0|0-1|½-½|1/2-1/2)\b'),
            'squares': re.compile(r'\b[a-h][1-8]\b'),
            'piece_symbols': re.compile(r'[♔♕♖♗♘♙♚♛♜♝♞♟]'),
            'variations': re.compile(r'\([^\)]+\)'),
            'advanced_eval': re.compile(r'(?:[\+\-]?\d+\.\d+|\(\d+:\d+\))')
        }

    def _init_chess_keywords(self) -> Set[str]:
        """تهيئة الكلمات المحجوزة في الشطرنج"""
        return {
            # قطع الشطرنج
            'King', 'Queen', 'Rook', 'Bishop', 'Knight', 'Pawn',
            'K', 'Q', 'R', 'B', 'N', 'P',
            # مصطلحات شائعة
            'check', 'mate', 'stalemate', 'draw',
            'castling', 'en passant', 'promotion',
            # مصطلحات عربية
            'شاه', 'ملك', 'وزير', 'فيل', 'حصان', 'طابية', 'بيدق',
            'كش', 'مات', 'تعادل'
        }

    def extract_from_pdf(self, pdf_path: str) -> List[Dict]:
        """استخراج النصوص من ملف PDF"""
        try:
            self.stats['total_pages'] = 0
            self.stats['processed_pages'] = 0
            pages_content = []

            with pdfplumber.open(pdf_path) as pdf:
                self.stats['total_pages'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, 1):
                    self.logger.info(f"معالجة الصفحة {page_num}/{self.stats['total_pages']}")
                    
                    page_content = self.process_page(page)
                    if page_content['blocks']:
                        pages_content.append(page_content)
                        self.stats['processed_pages'] += 1

            return pages_content

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الملف: {str(e)}")
            self.stats['processing_errors'] += 1
            return []

    def process_page(self, page) -> Dict:
        """معالجة صفحة واحدة"""
        try:
            # استخراج الكلمات مع المعلومات الإضافية
            words = self._extract_words_with_attributes(page)
            
            # تنظيف وتحسين النصوص
            cleaned_words = self._clean_words(words)
            
            # تحليل وتجميع الكتل
            blocks = self._analyze_and_group_blocks(cleaned_words)
            
            # استخراج الرسوم التوضيحية
            diagrams = self._extract_chess_diagrams(page)
            
            # تحديث الإحصائيات
            self._update_stats(blocks, diagrams)
            
            return {
                'page_number': page.page_number,
                'width': page.width,
                'height': page.height,
                'blocks': blocks,
                'diagrams': diagrams,
                'metadata': {
                    'has_chess_content': any(b['type'] == 'chess' for b in blocks),
                    'has_diagrams': bool(diagrams),
                    'processing_time': datetime.now().isoformat()
                }
            }

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الصفحة: {str(e)}")
            self.stats['processing_errors'] += 1
            return {'blocks': [], 'diagrams': [], 'metadata': {}}

    def _extract_words_with_attributes(self, page) -> List[Dict]:
        """استخراج الكلمات مع خصائصها"""
        return page.extract_words(
            keep_blank_chars=True,
            extra_attrs=['fontname', 'size', 'object_type', 'upright', 'strokewidth'],
            x_tolerance=self.config_params['x_tolerance'],
            y_tolerance=self.config_params['y_tolerance']
        )

    def _clean_words(self, words: List[Dict]) -> List[Dict]:
        """تنظيف وتحسين الكلمات المستخرجة"""
        cleaned = []
        for word in words:
            if not word['text'].strip():
                continue
                
            word['text'] = self._clean_text(word['text'])
            word['language'] = self._detect_text_language(word['text'])
            word['direction'] = 'rtl' if word['language'] == 'ar' else 'ltr'
            
            cleaned.append(word)
        return cleaned

    def _clean_text(self, text: str) -> str:
        """تنظيف النص من الأحرف غير المرغوب فيها"""
        text = ' '.join(text.split())
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text.strip()

    def _detect_text_language(self, text: str) -> str:
        """تحديد لغة النص"""
        try:
            if any('\u0600' <= ch <= '\u06FF' for ch in text):
                return 'ar'
            return 'en'
        except:
            return 'en'

    def _analyze_and_group_blocks(self, words: List[Dict]) -> List[Dict]:
        """تحليل وتجميع الكلمات في كتل"""
        blocks = []
        current_block = []
        current_y = None
        
        for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
            if current_y is None:
                current_y = word['top']
                current_block = [word]
            elif abs(word['top'] - current_y) <= self.config_params['line_margin']:
                current_block.append(word)
            else:
                if current_block:
                    block = self._create_content_block(current_block)
                    if block:
                        blocks.append(block)
                current_block = [word]
                current_y = word['top']
        
        if current_block:
            block = self._create_content_block(current_block)
            if block:
                blocks.append(block)
        
        return blocks

    def _create_content_block(self, words: List[Dict]) -> Optional[Dict]:
        """إنشاء كتلة محتوى مع تحليلها"""
        if not words or len(words) < self.config_params['min_block_size']:
            return None

        text = ' '.join(w['text'] for w in words)
        block_type, content_info = self._analyze_text_content(text)
        
        return {
            'text': text,
            'bbox': self._calculate_bbox(words),
            'font': words[0].get('fontname', ''),
            'size': words[0].get('size', 0),
            'language': words[0].get('language', 'en'),
            'direction': words[0].get('direction', 'ltr'),
            'type': block_type,
            'needs_translation': block_type == 'regular' and words[0].get('language') == 'en',
            'metadata': {
                'is_bold': any(w.get('strokewidth', 0) > 0 for w in words),
                'word_count': len(words),
                'content_info': content_info
            }
        }

    def _calculate_bbox(self, words: List[Dict]) -> Tuple[float, float, float, float]:
        """حساب الإطار المحيط للكتلة"""
        return (
            min(w['x0'] for w in words),
            min(w['top'] for w in words),
            max(w['x1'] for w in words),
            max(w['bottom'] for w in words)
        )

    def _analyze_text_content(self, text: str) -> Tuple[str, Dict]:
        """تحليل محتوى النص وتصنيفه"""
        content_info = {
            'chess_elements': [],
            'has_moves': False,
            'has_evaluation': False,
            'has_annotation': False,
            'has_variation': False
        }

        # فحص الكلمات المحجوزة
        if any(keyword in text for keyword in self.chess_keywords):
            content_info['has_chess_keywords'] = True
            return 'chess', content_info

        # فحص أنماط الشطرنج
        for pattern_name, pattern in self.chess_patterns.items():
            matches = list(pattern.finditer(text))
            if matches:
                elements = [m.group() for m in matches]
                content_info['chess_elements'].extend(elements)
                
                if pattern_name in ['piece_moves', 'pawn_moves', 'castling']:
                    content_info['has_moves'] = True
                elif pattern_name == 'evaluation':
                    content_info['has_evaluation'] = True
                elif pattern_name == 'annotation':
                    content_info['has_annotation'] = True
                elif pattern_name == 'variations':
                    content_info['has_variation'] = True

        return ('chess', content_info) if content_info['chess_elements'] else ('regular', content_info)

    def _update_stats(self, blocks: List[Dict], diagrams: List[Dict]):
        """تحديث إحصائيات المعالجة"""
        self.stats['total_blocks'] += len(blocks)
        self.stats['chess_blocks'] += sum(1 for b in blocks if b['type'] == 'chess')
        self.stats['text_blocks'] += sum(1 for b in blocks if b['type'] == 'regular')
        self.stats['diagrams'] += len(diagrams)

    def get_stats(self) -> Dict:
        """الحصول على الإحصائيات الحالية"""
        return self.stats


class TranslationProcessor:
    """معالج الترجمة الرئيسي مع دعم خاص لكتب الشطرنج"""
    
    def __init__(self, config_manager: ConfigManager, cache_manager: CacheManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.cache = cache_manager
        self.translator = Translator()
        self.batch_size = self.config.get('translation', {}).get('batch_size', 10)
        self.timeout = self.config.get('translation', {}).get('timeout', 30)
        self.retries = self.config.get('translation', {}).get('retries', 3)
        self.lock = threading.Lock()
        self.translation_count = 0
        
        # تهيئة الأنماط والقواعد
        self._init_patterns()
        
    def _init_patterns(self):
        """تهيئة أنماط التعرف على النصوص الخاصة"""
        self.chess_patterns = {
            'moves': re.compile(r'\b([KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b'),
            'castling': re.compile(r'\b(O-O(?:-O)?)\b'),
            'move_numbers': re.compile(r'\b(\d+\.)\b'),
            'results': re.compile(r'\b(1-0|0-1|1/2-1/2|\½-\½)\b'),
            'annotations': re.compile(r'[!?]{1,2}')
        }
        
        self.protected_terms = set([
            'K', 'Q', 'R', 'B', 'N',  # قطع الشطرنج
            '+', '#', 'x', '=',       # رموز خاصة
            'e.p.', 'ep'              # أخرى
        ])

    def translate_page(self, page_content: Dict) -> Dict:
        """ترجمة محتوى صفحة كاملة"""
        if not page_content or 'blocks' not in page_content:
            return page_content

        translated_page = page_content.copy()
        translated_blocks = []

        for block in page_content['blocks']:
            translated_block = self._translate_block(block)
            if translated_block:
                translated_blocks.append(translated_block)

        translated_page['blocks'] = translated_blocks
        return translated_page

    def _translate_block(self, block: Dict) -> Dict:
        """ترجمة كتلة نصية واحدة"""
        try:
            if not block.get('text', '').strip():
                return block

            text = block['text']
            
            # حماية النصوص الخاصة
            protected_text, placeholders = self._protect_special_content(text)
            
            # ترجمة النص المحمي
            translated_text = self._translate_with_retry(protected_text)
            
            # استعادة النصوص المحمية
            final_text = self._restore_protected_content(translated_text, placeholders)
            
            # تحديث الكتلة
            block['original_text'] = text
            block['translated_text'] = final_text
            
            if final_text != text:
                self.translation_count += 1
                
            return block

        except Exception as e:
            self.logger.error(f"خطأ في ترجمة الكتلة: {str(e)}")
            return block

    def _protect_special_content(self, text: str) -> Tuple[str, Dict[str, str]]:
        """حماية المحتوى الخاص من الترجمة"""
        protected_text = text
        placeholders = {}
        placeholder_counter = 0

        # حماية نقلات الشطرنج
        for pattern_name, pattern in self.chess_patterns.items():
            matches = pattern.finditer(protected_text)
            for match in matches:
                placeholder = f"[CHESS_{placeholder_counter}]"
                placeholders[placeholder] = match.group()
                protected_text = protected_text.replace(match.group(), placeholder)
                placeholder_counter += 1

        # حماية المصطلحات المحجوزة
        words = protected_text.split()
        protected_words = []
        
        for word in words:
            if word in self.protected_terms:
                placeholder = f"[TERM_{placeholder_counter}]"
                placeholders[placeholder] = word
                protected_words.append(placeholder)
                placeholder_counter += 1
            else:
                protected_words.append(word)
        
        protected_text = ' '.join(protected_words)
        return protected_text, placeholders

    def _translate_with_retry(self, text: str) -> str:
        """ترجمة النص مع إعادة المحاولة"""
        if not text.strip():
            return text

        # التحقق من الذاكرة المؤقتة
        cached = self.cache.get_translation(text)
        if cached:
            return cached

        for attempt in range(self.retries):
            try:
                with self.lock:
                    translation = self.translator.translate(
                        text,
                        dest='ar',
                        src='en',
                        timeout=self.timeout
                    )
                    
                if translation and translation.text:
                    # تخزين في الذاكرة المؤقتة
                    self.cache.store_translation(text, translation.text)
                    return translation.text
                    
            except Exception as e:
                self.logger.warning(f"محاولة الترجمة {attempt + 1} فشلت: {str(e)}")
                if attempt < self.retries - 1:
                    time.sleep(1)
                    
        return text

    def _restore_protected_content(self, text: str, placeholders: Dict[str, str]) -> str:
        """استعادة المحتوى المحمي"""
        restored_text = text
        for placeholder, original in placeholders.items():
            restored_text = restored_text.replace(placeholder, original)
        return restored_text

    def translate_batch(self, blocks: List[Dict]) -> List[Dict]:
        """ترجمة مجموعة من الكتل"""
        translated_blocks = []
        
        with ThreadPoolExecutor(max_workers=min(10, len(blocks))) as executor:
            futures = []
            for block in blocks:
                future = executor.submit(self._translate_block, block)
                futures.append(future)
            
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="ترجمة الكتل",
                unit="كتلة"
            ):
                try:
                    result = future.result()
                    translated_blocks.append(result)
                except Exception as e:
                    self.logger.error(f"خطأ في ترجمة الكتلة: {str(e)}")
                    
        return translated_blocks

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الترجمة"""
        return {
            'translated_blocks': self.translation_count,
            'cache_hits': len(self.cache.cache) if self.cache else 0,
            'batch_size': self.batch_size,
            'retries': self.retries
        }

    def cleanup(self):
        """تنظيف وحفظ البيانات"""
        try:
            if self.cache:
                self.cache.save_cache()
        except Exception as e:
            self.logger.error(f"خطأ في حفظ الذاكرة المؤقتة: {str(e)}")
    

class PDFProcessor:
    """معالج ملفات PDF المتخصص في كتب الشطرنج"""
    
    def __init__(self, config_manager: ConfigManager, cache_manager: CacheManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.cache = cache_manager
        self.translation_processor = TranslationProcessor(config_manager, cache_manager)
        self.text_extractor = TextExtractor(config_manager)  # تحديث مع config_manager
        self.block_manager = TextBlockManager(config_manager)  # إضافة BlockManager
        self.text_extractor.block_manager = self.block_manager  # ربط المكونات
        self.font_manager = FontManager(config_manager)
        self.stats = self._init_stats()

    def _init_stats(self) -> Dict:
        """تهيئة الإحصائيات"""
        return {
            'total_pages': 0,
            'processed_pages': 0,
            'translated_blocks': 0,
            'chess_moves': 0,
            'diagrams': 0,
            'annotations': 0,
            'start_time': None,
            'end_time': None,
            'total_blocks': 0,
            'failed_translations': 0,
            'processing_time': 0
        }

    def process_pdf(self, input_path: str, output_path: str) -> bool:
        """معالجة ملف PDF"""
        try:
            self.stats['start_time'] = datetime.now()
            self.logger.info(f"بدء معالجة الملف: {input_path}")

            # استخراج النصوص من الملف
            with pdfplumber.open(input_path) as pdf:
                self.stats['total_pages'] = len(pdf.pages)
                processed_pages = []

                for page_num, page in enumerate(tqdm(pdf.pages, desc="تقدم المعالجة"), 1):
                    self.logger.info(f"معالجة صفحة {page_num}")
                    
                    # استخراج وتحليل الكتل
                    blocks = self.block_manager.process_page_content(page)
                    
                    # معالجة وترجمة المحتوى
                    processed_page = self._process_page_blocks(blocks, page.width, page.height)
                    processed_pages.append(processed_page)
                    self.stats['processed_pages'] += 1

            # إنشاء PDF المترجم
            self._create_output_pdf(processed_pages, output_path)
            
            # حفظ التقرير والإحصائيات
            self._finalize_processing(output_path)
            
            return True

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الملف PDF: {str(e)}")
            return False

    def _process_page_blocks(self, blocks: List[Dict], width: float, height: float) -> Dict:
        """معالجة كتل الصفحة"""
        processed_blocks = []

        self.logger.info(f"عدد الكتل المكتشفة: {len(blocks)}")  # إضافة

        for block in blocks:
            try:
                self.stats['total_blocks'] += 1
                
                # طباعة معلومات عن نوع الكتلة
                self.logger.debug(f"نوع الكتلة: {block['type']}, اللغة: {block.get('language', 'غير محدد')}")  # إضافة
                
                if block['type'] == 'chess':
                    chess_elements = block.get('metadata', {}).get('chess_elements', [])
                    self.stats['chess_moves'] += len(chess_elements)
                    self.logger.debug(f"تم اكتشاف {len(chess_elements)} حركة شطرنج")  # إضافة
                    processed_blocks.append(block)
                    
                elif block.get('needs_translation', False):
                    self.logger.debug(f"محاولة ترجمة نص: {block['text'][:50]}...")  # إضافة
                    translated_block = self._translate_block(block)
                    processed_blocks.append(translated_block)
                    
                else:
                    processed_blocks.append(block)

            except Exception as e:
                self.logger.error(f"خطأ في معالجة كتلة: {str(e)}")
                processed_blocks.append(block)
                self.stats['failed_translations'] += 1

        self.logger.info(f"تمت معالجة {len(processed_blocks)} كتلة")  # إضافة

        return {
            'blocks': processed_blocks,
            'width': width,
            'height': height
        }

    def _translate_block(self, block: Dict) -> Dict:
        """ترجمة كتلة نصية واحدة"""
        translated_block = block.copy()
        try:
            translated_text = self.translation_processor.translate_text(block['text'])
            if translated_text and translated_text != block['text']:
                translated_block['translated_text'] = translated_text
                translated_block['original_text'] = block['text']
                self.stats['translated_blocks'] += 1
        except Exception as e:
            self.logger.error(f"خطأ في ترجمة النص: {str(e)}")
            translated_block['translated_text'] = block['text']
            self.stats['failed_translations'] += 1

        return translated_block

    def _create_output_pdf(self, pages: List[Dict], output_path: str):
        """إنشاء PDF المترجم"""
        try:
            c = canvas.Canvas(output_path, pagesize=(pages[0]['width'], pages[0]['height']))

            for page in pages:
                # رسم النصوص
                for block in page['blocks']:
                    self._draw_block(c, block)
                c.showPage()

            c.save()
            self.logger.info(f"تم حفظ الملف بنجاح: {output_path}")

        except Exception as e:
            self.logger.error(f"خطأ في إنشاء PDF: {str(e)}")
            raise

    def _draw_block(self, canvas_obj, block: Dict):
        """رسم كتلة نصية على PDF"""
        try:
            text = block.get('translated_text', block['text'])
            x, y = block['bbox'][0], block['bbox'][3]
            
            if block['type'] == 'chess':
                font_name = "Helvetica"
            else:
                if block['language'] == 'ar':
                    text = arabic_reshaper.reshape(text)
                    text = get_display(text)
                    font_name = "Amiri-Regular"
                else:
                    font_name = "Helvetica"

            size = block['size'] or 12
            canvas_obj.setFont(font_name, size)
            canvas_obj.drawString(x, y, text)

        except Exception as e:
            self.logger.error(f"خطأ في رسم الكتلة: {str(e)}")

    def _finalize_processing(self, output_path: str):
        """إنهاء المعالجة وحفظ التقارير"""
        self.stats['end_time'] = datetime.now()
        self.stats['processing_time'] = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        # دمج إحصائيات المكونات
        self.stats.update(self.block_manager.get_stats())
        
        # حفظ التقرير المفصل
        self._save_detailed_report(output_path)
        self.cache.save_cache()

    def _save_detailed_report(self, output_path: str):
        """حفظ تقرير مفصل"""
        try:
            report = {
                'general_stats': {
                    'total_pages': self.stats['total_pages'],
                    'processed_pages': self.stats['processed_pages'],
                    'total_blocks': self.stats['total_blocks'],
                    'processing_time': self.stats['processing_time']
                },
                'content_stats': {
                    'chess_blocks': self.stats.get('chess_blocks', 0),
                    'text_blocks': self.stats.get('text_blocks', 0),
                    'chess_moves': self.stats['chess_moves'],
                    'diagrams': self.stats['diagrams'],
                    'annotations': self.stats['annotations']
                },
                'translation_stats': {
                    'translated_blocks': self.stats['translated_blocks'],
                    'failed_translations': self.stats['failed_translations']
                },
                'timing': {
                    'start_time': self.stats['start_time'].isoformat(),
                    'end_time': self.stats['end_time'].isoformat(),
                    'duration_seconds': self.stats['processing_time']
                },
                'metadata': {
                    'version': '2.0.0',
                    'timestamp': datetime.now().isoformat(),
                    'user': os.getenv('USER', 'x9ci')
                }
            }
            
            # طباعة إحصائيات إضافية
            print("\nإحصائيات مفصلة:")
            print(f"إجمالي الكتل: {self.stats['total_blocks']}")
            print(f"كتل الشطرنج: {self.stats.get('chess_blocks', 0)}")
            print(f"كتل النص: {self.stats.get('text_blocks', 0)}")
            print(f"حركات الشطرنج: {self.stats['chess_moves']}")
            print(f"الكتل المترجمة: {self.stats['translated_blocks']}")
            print(f"الترجمات الفاشلة: {self.stats['failed_translations']}")
            
            report_path = output_path.replace('.pdf', '.report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=4)
            
            self.logger.info(f"تم حفظ تقرير المعالجة في: {report_path}")

        except Exception as e:
            self.logger.error(f"خطأ في حفظ التقرير: {str(e)}")
            
               

class PageProcessor:
    """معالج الصفحات وترجمة النصوص"""
    
    def __init__(self, text_processor):
        self.text_processor = text_processor
        self.batch_size = 10
        self.processed_blocks = set()
        self.font_size = 12
        self.stats = {
            'processed_blocks': 0,
            'translated_blocks': 0,
            'errors': []
        }

    def process_page(self, page_content, page_num: int):
        """
        معالجة صفحة كاملة
        
        Args:
            page_content: محتوى الصفحة
            page_num: رقم الصفحة
            
        Returns:
            List[Dict]: الكتل المترجمة
        """
        logging.info(f"معالجة الصفحة {page_num + 1}")
        translated_blocks = []
        text_batch = []
        blocks_to_process = []
        
        if not page_content:
            logging.warning(f"لا يوجد محتوى في الصفحة {page_num + 1}")
            return []
            
        try:
            # ترتيب المحتوى من أعلى إلى أسفل ومن اليمين إلى اليسار
            sorted_content = sorted(
                page_content,
                key=lambda x: (-float(x.get('bbox', (0,0,0,0))[1]), -float(x.get('bbox', (0,0,0,0))[0]))
            )

            for block in sorted_content:
                try:
                    if not self._validate_block(block):
                        continue

                    text = self.text_processor.clean_text(block.get('text', ''))
                    if not self._should_process_text(text):
                        continue

                    text_batch.append(text)
                    blocks_to_process.append(block)

                    if len(text_batch) >= self.batch_size:
                        self.process_and_add_translations(
                            text_batch, blocks_to_process, translated_blocks, page_num
                        )
                        text_batch = []
                        blocks_to_process = []

                except Exception as e:
                    self._log_error(f"خطأ في معالجة كتلة النص", e, page_num)
                    continue

            # معالجة الكتل المتبقية
            if text_batch:
                self.process_and_add_translations(
                    text_batch, blocks_to_process, translated_blocks, page_num
                )

            return translated_blocks
                
        except Exception as e:
            self._log_error(f"خطأ في معالجة الصفحة {page_num + 1}", e, page_num)
            return []

    
    def process_page(self, page_content, page_num: int):
        """
        معالجة صفحة كاملة
        
        Args:
            page_content: محتوى الصفحة
            page_num: رقم الصفحة
            
        Returns:
            List[Dict]: الكتل المترجمة
        """
        logging.info(f"معالجة الصفحة {page_num + 1}")
        translated_blocks = []
        text_batch = []
        blocks_to_process = []
        
        if not page_content:
            logging.warning(f"لا يوجد محتوى في الصفحة {page_num + 1}")
            return []
            
        try:
            # ترتيب المحتوى من أعلى إلى أسفل ومن اليمين إلى اليسار
            sorted_content = sorted(
                page_content,
                key=lambda x: (-float(x.get('bbox', (0,0,0,0))[1]), -float(x.get('bbox', (0,0,0,0))[0]))
            )

            for block in sorted_content:
                try:
                    if not self._validate_block(block):
                        continue

                    text = self.text_processor.clean_text(block.get('text', ''))
                    if not self._should_process_text(text):
                        continue

                    text_batch.append(text)
                    blocks_to_process.append(block)

                    if len(text_batch) >= self.batch_size:
                        self.process_and_add_translations(
                            text_batch, blocks_to_process, translated_blocks, page_num
                        )
                        text_batch = []
                        blocks_to_process = []

                except Exception as e:
                    self._log_error(f"خطأ في معالجة كتلة النص", e, page_num)
                    continue

            # معالجة الكتل المتبقية
            if text_batch:
                self.process_and_add_translations(
                    text_batch, blocks_to_process, translated_blocks, page_num
                )

            return translated_blocks
                
        except Exception as e:
            self._log_error(f"خطأ في معالجة الصفحة {page_num + 1}", e, page_num)
            return []

    
    def _validate_block(self, block: Dict) -> bool:
        """التحقق من صحة الكتلة"""
        return (
            isinstance(block, dict) and
            'text' in block and
            'bbox' in block and
            len(block['bbox']) == 4
        )

    def _should_process_text(self, text: str) -> bool:
        """التحقق مما إذا كان يجب معالجة النص"""
        return (
            len(text.strip()) >= 3 and
            not self.text_processor.is_chess_notation(text)
        )

    def process_and_add_translations(self, texts: List[str], blocks: List[Dict], 
                                  translated_blocks: List[Dict], page_num: int):
        """معالجة وإضافة الترجمات"""
        try:
            print(f"معالجة {len(texts)} نص للترجمة")
            translations = self.text_processor.process_text_batch(texts)
            
            for trans, block in zip(translations, blocks):
                try:
                    if trans and trans.strip():
                        # إضافة معلومات الترجمة
                        translated_block = {
                            'text': trans,
                            'bbox': block['bbox'],
                            'original_bbox': block['bbox'],
                            'type': 'text',
                            'page': page_num,
                            'original': block.get('text', ''),
                            'font': block.get('font', 'Arabic'),
                            'size': block.get('size', self.font_size),
                            'timestamp': datetime.utcnow().isoformat()
                        }
                        
                        translated_blocks.append(translated_block)
                        self.stats['translated_blocks'] += 1
                        self.stats['processed_blocks'] += 1
                        print(f"تمت إضافة الترجمة: {trans}")
                        
                except Exception as e:
                    self._log_error("خطأ في إضافة الترجمة للكتلة", e, page_num)
                    continue
                    
        except Exception as e:
            self._log_error("خطأ في معالجة دفعة الترجمة", e, page_num)

    def _log_error(self, message: str, error: Exception, page_num: int):
        """تسجيل الأخطاء"""
        error_info = {
            'message': message,
            'error': str(error),
            'page': page_num,
            'time': datetime.utcnow().isoformat()
        }
        self.stats['errors'].append(error_info)
        print(f"{message}: {str(error)}")
        logging.error(f"{message}: {str(error)}")

    # ... (باقي الدوال بدون تغيير)
    
    def process_and_add_translations(self, texts: List[str], blocks: List[Dict], 
                                  translated_blocks: List[Dict], page_num: int):
        """معالجة وإضافة الترجمات"""
        try:
            print(f"معالجة {len(texts)} نص للترجمة")
            translations = self.text_processor.process_text_batch(texts)
            
            for trans, block in zip(translations, blocks):
                try:
                    if trans and trans.strip():
                        # إضافة معلومات الترجمة
                        translated_block = {
                            'text': trans,
                            'bbox': block['bbox'],
                            'original_bbox': block['bbox'],
                            'type': 'text',
                            'page': page_num,
                            'original': block.get('text', '')
                        }
                        
                        translated_blocks.append(translated_block)
                        self.stats['translated_blocks'] += 1
                        print(f"تمت إضافة الترجمة: {trans}")
                        
                except Exception as e:
                    print(f"خطأ في إضافة الترجمة للكتلة: {str(e)}")
                    self.stats['errors'].append({
                        'page': page_num,
                        'error': str(e),
                        'time': datetime.now().isoformat()
                    })
                    continue
                    
        except Exception as e:
            print(f"خطأ في معالجة دفعة الترجمة: {str(e)}")
            logging.error(f"خطأ في معالجة دفعة الترجمة: {str(e)}")
            self.stats['errors'].append({
                'page': page_num,
                'error': str(e),
                'time': datetime.now().isoformat()
            })

    def create_translated_overlay(self, translated_blocks, page_num, page_size):
        """إنشاء طبقة الترجمة"""
        try:
            packet = BytesIO()
            width, height = float(page_size[0]), float(page_size[1])
            c = canvas.Canvas(packet, pagesize=(width, height))
            used_positions = []
            
            print(f"إنشاء طبقة الترجمة للصفحة {page_num + 1}")
            print(f"عدد الكتل المترجمة: {len(translated_blocks)}")

            for block in translated_blocks:
                try:
                    if block['type'] != 'text':
                        continue

                    text = block['text']
                    if not text:
                        continue

                    # حساب أبعاد النص
                    text_width, text_height = self.calculate_text_dimensions(text)
                    
                    # تحديد الموقع
                    bbox = block['original_bbox']
                    x, y = self.find_optimal_position(
                        bbox, text_width, text_height, used_positions, width, height
                    )

                    # رسم خلفية بيضاء شفافة
                    self.draw_text_background(c, x, y, text_width, text_height)
                    
                    # كتابة النص العربي
                    c.setFont("Arabic", self.font_size)
                    c.setFillColorRGB(0, 0, 0)  # لون أسود للنص
                    c.drawRightString(x + text_width, y + text_height, text)
                    
                    # رسم خط توضيحي
                    self.draw_connection_line(c, x, y, bbox, text_width, text_height, height)
                    used_positions.append((x, y, text_width, text_height))

                except Exception as e:
                    print(f"خطأ في معالجة كتلة نص: {str(e)}")
                    continue

            c.save()
            packet.seek(0)
            return packet

        except Exception as e:
            print(f"خطأ في إنشاء طبقة الترجمة: {str(e)}")
            # إنشاء صفحة فارغة في حالة الخطأ
            empty_packet = BytesIO()
            c = canvas.Canvas(empty_packet, pagesize=(width, height))
            c.save()
            empty_packet.seek(0)
            return empty_packet

    def calculate_text_dimensions(self, text: str) -> tuple:
        """حساب أبعاد النص"""
        return len(text) * self.font_size * 0.6, self.font_size * 1.2

    def find_optimal_position(self, bbox, text_width, text_height, used_positions, 
                           page_width, page_height):
        """إيجاد أفضل موقع للنص المترجم"""
        x = bbox[0]
        y = page_height - bbox[3] - text_height - 5
        
        x = max(5, min(x, page_width - text_width - 5))
        y = max(5, min(y, page_height - text_height - 5))
        
        while self.check_overlap((x, y, text_width, text_height), used_positions):
            y -= text_height + 5
            if y < 5:
                y = page_height - text_height - 5
                x += text_width + 10
                if x + text_width > page_width - 5:
                    x = 5
                    y = page_height - text_height - 5
                    break

        return x, y

    def check_overlap(self, current_rect, used_positions):
        """التحقق من تداخل النصوص"""
        x, y, w, h = current_rect
        for used_x, used_y, used_w, used_h in used_positions:
            if (x < used_x + used_w and x + w > used_x and
                y < used_y + used_h and y + h > used_y):
                return True
        return False

    def draw_text_background(self, canvas_obj, x, y, width, height):
        """رسم خلفية شفافة للنص"""
        try:
            padding = 4
            canvas_obj.setFillColorRGB(1, 1, 1, 0.8)
            canvas_obj.setStrokeColorRGB(0.9, 0.9, 0.9, 0.3)
            canvas_obj.rect(
                x - padding,
                y - padding,
                width + (2 * padding),
                height + (2 * padding),
                fill=True,
                stroke=True
            )
        except Exception as e:
            logging.error(f"خطأ في رسم خلفية النص: {str(e)}")

    def draw_connection_line(self, canvas_obj, x, y, bbox, text_width, text_height, page_height):
        """رسم خط يربط النص المترجم بالنص الأصلي"""
        try:
            canvas_obj.setStrokeColorRGB(0.7, 0.7, 0.7, 0.5)
            canvas_obj.setLineWidth(0.3)
            start_x = x + text_width / 2
            start_y = y + text_height / 2
            end_x = (bbox[0] + bbox[2]) / 2
            end_y = page_height - ((bbox[1] + bbox[3]) / 2)
            canvas_obj.line(start_x, start_y, end_x, end_y)
        except Exception as e:
            logging.error(f"خطأ في رسم خط الربط: {str(e)}")

    def get_statistics(self) -> Dict:
        """الحصول على إحصائيات المعالجة"""
        return self.stats

class PDFHandler:
    """معالج ملفات PDF الرئيسي مع دعم معالجة الأخطاء المتقدمة"""
    
    def __init__(self, config, page_processor):
        """تهيئة معالج PDF مع الإعدادات والمعالج المخصص للصفحات"""
        self.config = config
        self.page_processor = page_processor
        self.temp_dir = tempfile.mkdtemp()
        self.current_pdf_path = None
        self.writer = PdfWriter()
        self.current_pdf = None
        self.modified_pages = set()  # استخدام set لتجنب التكرار
        
        # إحصائيات وتتبع الأخطاء
        self.stats = {
            'processed_pages': 0,
            'translated_blocks': 0,
            'skipped_pages': 0,
            'total_pages': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
        
        # إعداد التسجيل
        self._setup_logging()
        
    def _setup_logging(self):
        """إعداد نظام تسجيل الأحداث"""
        try:
            log_dir = Path('logs')
            log_dir.mkdir(exist_ok=True)
            
            log_file = log_dir / f"pdf_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file),
                    logging.StreamHandler()
                ]
            )
            
            self.logger = logging.getLogger(__name__)
            self.logger.info("تم تهيئة نظام التسجيل بنجاح")
            
        except Exception as e:
            print(f"خطأ في إعداد نظام التسجيل: {str(e)}")
            raise

    def _initialize_processing(self, input_path: str) -> Tuple[Path, Path]:
        """تهيئة عملية المعالجة وإعداد المسارات"""
        try:
            input_path = Path(input_path)
            self.stats['start_time'] = datetime.now()
            
            if not input_path.exists():
                raise FileNotFoundError(f"الملف غير موجود: {input_path}")
            
            if not input_path.suffix.lower() == '.pdf':
                raise ValueError("الملف يجب أن يكون بصيغة PDF")
            
            self.current_pdf_path = str(input_path)
            
            # إنشاء مجلد المخرجات إذا لم يكن موجوداً
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # إنشاء اسم الملف الناتج
            output_path = output_dir / f"translated_{input_path.stem}.pdf"
            
            return input_path, output_path
            
        except Exception as e:
            self.logger.error(f"خطأ في تهيئة المعالجة: {str(e)}")
            raise

    def _check_page_content(self, page) -> bool:
        """التحقق من محتوى الصفحة قبل المعالجة"""
        try:
            # استخراج النص
            text = page.extract_text()
            if not text.strip():
                return False

            # استخراج الكلمات
            words = page.extract_words()
            if not words:
                return False

            # التحقق من وجود صور
            images = page.images
            if not words and not images:
                return False

            return True
        except Exception as e:
            self.logger.error(f"خطأ في فحص محتوى الصفحة: {str(e)}")
            return False
    
    def translate_pdf(self, input_path: str, output_path: str = None) -> bool:
        """الدالة الرئيسية لترجمة ملف PDF"""
        try:
            # تهيئة المعالجة
            input_path, output_path = self._initialize_processing(input_path)
            self.logger.info(f"بدء معالجة الملف: {input_path}")

            if not self.validate_pdf(str(input_path)):
                raise ValueError("ملف PDF غير صالح أو تالف")

            with pdfplumber.open(str(input_path)) as plumber_pdf:
                self.current_pdf = PdfReader(str(input_path))
                total_pages = len(plumber_pdf.pages)
                self.stats['total_pages'] = total_pages

                # إنشاء شريط التقدم
                with tqdm(total=total_pages, desc="تقدم المعالجة") as progress_bar:
                    for page_num in range(total_pages):
                        try:
                            success = self._process_single_page(
                                plumber_pdf.pages[page_num],
                                page_num,
                                progress_bar
                            )
                            if not success:
                                self.stats['skipped_pages'] += 1

                        except Exception as e:
                            self._handle_page_error(page_num, e)
                            continue

                # حفظ الملف النهائي
                return self._save_final_pdf(output_path)

        except Exception as e:
            self.logger.error(f"خطأ في عملية الترجمة: {str(e)}")
            raise
        finally:
            self.cleanup()

    def _process_single_page(self, page, page_num: int, progress_bar) -> bool:
        """معالجة صفحة واحدة من PDF"""
        try:
            self.logger.info(f"معالجة صفحة {page_num + 1}")
            
            # استخراج النص
            text_content = self.extract_words_safely(page)
            if not text_content:
                return False

            # معالجة النص
            translated_blocks = self.page_processor.process_page(text_content, page_num)
            if not translated_blocks:
                return False

            # إنشاء وإضافة الترجمة
            self._add_translation_to_page(
                translated_blocks,
                page_num,
                (float(page.width), float(page.height))
            )

            # تحديث الإحصائيات
            self.stats['processed_pages'] += 1
            self.stats['translated_blocks'] += len(translated_blocks)
            self.modified_pages.add(page_num)

            # تحديث شريط التقدم
            if progress_bar:
                progress_bar.update(1)

            # تحسين الذاكرة كل 5 صفحات
            if page_num % 5 == 0:
                self.optimize_memory_usage()

            return True

        except Exception as e:
            self._handle_page_error(page_num, e)
            return False

    def _add_translation_to_page(self, translated_blocks: list, page_num: int, page_dimensions: Tuple[float, float]):
        """إضافة الترجمة إلى الصفحة"""
        try:
            width, height = page_dimensions
            overlay_packet = self.page_processor.create_translated_overlay(
                translated_blocks,
                page_num,
                (width, height)
            )

            if overlay_packet:
                overlay_pdf = PdfReader(overlay_packet)
                page_obj = self.current_pdf.pages[page_num]
                page_obj.merge_page(overlay_pdf.pages[0])
                self.writer.add_page(page_obj)
            else:
                self.writer.add_page(self.current_pdf.pages[page_num])

        except Exception as e:
            self.logger.error(f"خطأ في إضافة الترجمة للصفحة {page_num + 1}: {str(e)}")
            self.writer.add_page(self.current_pdf.pages[page_num])
            raise

    def _handle_page_error(self, page_num: int, error: Exception):
        """معالجة أخطاء الصفحات"""
        error_msg = f"خطأ في معالجة الصفحة {page_num + 1}: {str(error)}"
        self.logger.error(error_msg)
        self.stats['errors'].append({
            'page': page_num + 1,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        })
        
        # إضافة الصفحة الأصلية بدون تعديل
        if self.current_pdf and page_num < len(self.current_pdf.pages):
            self.writer.add_page(self.current_pdf.pages[page_num])
    
    def validate_pdf(self, file_path: str) -> bool:
        """التحقق من صلاحية ملف PDF بشكل شامل"""
        try:
            # التحقق من وجود الملف
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"الملف غير موجود: {file_path}")

            # التحقق من حجم الملف
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise ValueError("ملف PDF فارغ")

            if file_size > self.config.max_file_size:
                raise ValueError(f"حجم الملف يتجاوز الحد المسموح: {file_size} bytes")

            # التحقق من صحة PDF
            with open(file_path, 'rb') as file:
                pdf = PdfReader(file)
                if len(pdf.pages) == 0:
                    raise ValueError("ملف PDF لا يحتوي على صفحات")
                
                # التحقق من إمكانية قراءة الصفحات
                for i, page in enumerate(pdf.pages):
                    if not hasattr(page, 'extract_text'):
                        raise ValueError(f"الصفحة {i+1} غير قابلة للقراءة")

            return True

        except Exception as e:
            self.logger.error(f"فشل التحقق من صلاحية PDF: {str(e)}")
            return False

    def extract_words_safely(self, page) -> list:
        """استخراج الكلمات من الصفحة بشكل آمن مع معالجة محسنة"""
        try:
            extracted_words = page.extract_words(
                keep_blank_chars=True,
                x_tolerance=3,
                y_tolerance=3,
                extra_attrs=['fontname', 'size', 'object_type', 'color']
            )

            processed_words = []
            for word in extracted_words:
                if not word.get('text', '').strip():
                    continue

                # تنظيف وتحسين البيانات المستخرجة
                processed_word = {
                    'text': word['text'].strip(),
                    'x0': round(float(word['x0']), 2),
                    'y0': round(float(word['y0']), 2),
                    'x1': round(float(word['x1']), 2),
                    'y1': round(float(word['y1']), 2),
                    'fontname': word.get('fontname', 'Unknown'),
                    'size': round(float(word.get('size', 0)), 1),
                    'color': word.get('color', (0, 0, 0)),
                    'object_type': word.get('object_type', 'text')
                }
                processed_words.append(processed_word)

            return processed_words

        except Exception as e:
            self.logger.error(f"خطأ في استخراج الكلمات: {str(e)}")
            return []

    def optimize_memory_usage(self):
        """تحسين استخدام الذاكرة مع مراقبة"""
        try:
            initial_memory = self._get_memory_usage()
            
            # تنظيف الذاكرة المؤقتة
            gc.collect()
            
            # إزالة الملفات المؤقتة غير المستخدمة
            self._clean_temp_files()
            
            final_memory = self._get_memory_usage()
            memory_freed = initial_memory - final_memory
            
            if memory_freed > 0:
                self.logger.debug(f"تم تحرير {memory_freed:.2f} MB من الذاكرة")

        except Exception as e:
            self.logger.warning(f"خطأ في تحسين الذاكرة: {str(e)}")

    def _get_memory_usage(self) -> float:
        """قياس استخدام الذاكرة الحالي"""
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # تحويل إلى ميجابايت

    def _clean_temp_files(self):
        """تنظيف الملفات المؤقتة بشكل آمن"""
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                for file_name in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, file_name)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        self.logger.warning(f"فشل في حذف الملف المؤقت {file_path}: {str(e)}")
                        
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف الملفات المؤقتة: {str(e)}")

    def cleanup(self):
        """تنظيف نهائي للموارد"""
        try:
            # إغلاق الملفات المفتوحة
            if hasattr(self, 'current_pdf'):
                del self.current_pdf
            
            if hasattr(self, 'writer'):
                del self.writer

            # حذف المجلد المؤقت
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            # تحرير الذاكرة
            gc.collect()
            
            self.logger.info("تم تنظيف جميع الموارد بنجاح")
            
        except Exception as e:
            self.logger.error(f"خطأ في التنظيف النهائي: {str(e)}")

    def get_statistics(self) -> dict:
        """الحصول على إحصائيات مفصلة للمعالجة"""
        stats = self.stats.copy()
        stats['end_time'] = datetime.now()
        
        if stats['start_time']:
            duration = (stats['end_time'] - stats['start_time']).total_seconds()
            stats['duration'] = f"{duration:.2f} seconds"
            
            if stats['total_pages'] > 0:
                stats['success_rate'] = f"{(stats['processed_pages'] / stats['total_pages']) * 100:.2f}%"
        
        return stats
    
    
    def save_pdf(self, output_path: str) -> bool:
        """واجهة لحفظ ملف PDF"""
        try:
            return self._save_final_pdf(Path(output_path))
        except Exception as e:
            self.logger.error(f"خطأ في حفظ ملف PDF: {str(e)}")
            return False
    
    def _save_final_pdf(self, output_path: Path) -> bool:
        """حفظ PDF النهائي مع المعالجة المتقدمة"""
        try:
            # إنشاء المجلد إذا لم يكن موجوداً
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # إضافة البيانات الوصفية
            self.writer.add_metadata({
                '/Producer': f'PDF Translator v{self.config.version}',
                '/CreationDate': datetime.now().strftime("D:%Y%m%d%H%M%S"),
                '/ModDate': datetime.now().strftime("D:%Y%m%d%H%M%S"),
                '/Creator': f'PDF Handler by {self.config.user}',
                '/ProcessedPages': str(self.stats['processed_pages'])
            })

            # حفظ الملف مع ضغط محسن
            with open(output_path, 'wb') as output_file:
                self.writer.write(output_file)

            self._save_processing_report(output_path)
            return True

        except Exception as e:
            self.logger.error(f"خطأ في حفظ PDF النهائي: {str(e)}")
            return False

    def _get_performance_metrics(self) -> dict:
        """حساب وإرجاع مقاييس الأداء للمعالجة"""
        try:
            metrics = {
                'processing_speed': 0,
                'memory_usage': 0,
                'success_rate': 0,
                'error_rate': 0,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # حساب سرعة المعالجة
            if self.stats['start_time'] and self.stats['end_time']:
                duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
                if duration > 0 and self.stats['processed_pages'] > 0:
                    metrics['processing_speed'] = self.stats['processed_pages'] / duration

            # حساب استخدام الذاكرة
            import psutil
            process = psutil.Process()
            metrics['memory_usage'] = process.memory_info().rss / 1024 / 1024  # تحويل إلى ميجابايت

            # حساب معدلات النجاح والخطأ
            if self.stats['total_pages'] > 0:
                metrics['success_rate'] = (self.stats['processed_pages'] / self.stats['total_pages']) * 100
                metrics['error_rate'] = (len(self.stats['errors']) / self.stats['total_pages']) * 100

            # إضافة معلومات إضافية
            metrics['processed_pages_per_second'] = metrics['processing_speed']
            metrics['average_memory_per_page'] = metrics['memory_usage'] / max(self.stats['processed_pages'], 1)

            return metrics

        except Exception as e:
            self.logger.error(f"خطأ في حساب مقاييس الأداء: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    
    def _save_processing_report(self, pdf_path: Path):
        """حفظ تقرير مفصل عن المعالجة"""
        try:
            # تحويل التواريخ إلى نصوص
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # تحضير الإحصائيات مع معالجة التواريخ
            stats = {
                'total_pages': self.stats['total_pages'],
                'processed_pages': self.stats['processed_pages'],
                'translated_blocks': self.stats['translated_blocks'],
                'skipped_pages': self.stats['skipped_pages'],
                'start_time': self.stats['start_time'].strftime("%Y-%m-%d %H:%M:%S") if self.stats['start_time'] else None,
                'end_time': current_time,
                'duration': f"{(datetime.now() - self.stats['start_time']).total_seconds():.2f} seconds" if self.stats['start_time'] else "0 seconds"
            }

            # تحضير التقرير
            report = {
                'file_info': {
                    'input_file': self.current_pdf_path,
                    'output_file': str(pdf_path),
                    'file_size': os.path.getsize(pdf_path),
                    'creation_date': current_time
                },
                'processing_stats': stats,
                'configuration': {
                    'processing_date': current_time
                },
                'performance': {
                    'memory_usage_mb': self._get_memory_usage(),
                    'processing_speed_pages_per_second': len(self.modified_pages) / max((datetime.now() - self.stats['start_time']).total_seconds(), 1) if self.stats['start_time'] else 0,
                    'success_rate': (self.stats['processed_pages'] / self.stats['total_pages'] * 100) if self.stats['total_pages'] > 0 else 0
                },
                'errors': [
                    {
                        'page': err.get('page'),
                        'error': str(err.get('error')),
                        'time': err.get('timestamp', current_time)
                    }
                    for err in self.stats['errors']
                ]
            }

            # حفظ التقرير
            report_path = pdf_path.with_suffix('.report.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"تم حفظ تقرير المعالجة في: {report_path}")

        except Exception as e:
            self.logger.error(f"خطأ في حفظ تقرير المعالجة: {str(e)}")

    def _get_memory_usage(self) -> float:
        """قياس استخدام الذاكرة الحالي بالميجابايت"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # تحويل إلى ميجابايت
        except:
            return 0.0
        
    def _get_warnings(self) -> List[dict]:
        """تجميع التحذيرات والملاحظات"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        warnings = []
        
        # تحذيرات الذاكرة
        memory_usage = self._get_memory_usage()
        if hasattr(self.config, 'memory_threshold') and memory_usage > self.config.memory_threshold:
            warnings.append({
                'type': 'memory_warning',
                'message': f'استخدام الذاكرة مرتفع: {memory_usage:.2f} MB',
                'time': current_time
            })

        # تحذيرات معدل النجاح
        if self.stats['total_pages'] > 0:
            success_rate = (self.stats['processed_pages'] / self.stats['total_pages']) * 100
            if success_rate < 90:
                warnings.append({
                    'type': 'success_rate_warning',
                    'message': f'معدل نجاح المعالجة منخفض: {success_rate:.2f}%',
                    'time': current_time
                })

        return warnings
    

    def _get_performance_metrics(self) -> dict:
        """حساب مقاييس الأداء"""
        metrics = {
            'processing_speed': 0,
            'memory_usage': self._get_memory_usage(),
            'success_rate': 0,
            'error_rate': 0
        }

        if self.stats['total_pages'] > 0:
            if self.stats['start_time'] and self.stats['end_time']:
                duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
                if duration > 0:
                    metrics['processing_speed'] = self.stats['processed_pages'] / duration

            metrics['success_rate'] = (self.stats['processed_pages'] / self.stats['total_pages']) * 100
            metrics['error_rate'] = (len(self.stats['errors']) / self.stats['total_pages']) * 100

        return metrics

    def _get_warnings(self) -> List[dict]:
        """تجميع التحذيرات والملاحظات"""
        warnings = []
        
        # تحذيرات الذاكرة
        memory_usage = self._get_memory_usage()
        if memory_usage > self.config.memory_threshold:
            warnings.append({
                'type': 'memory_warning',
                'message': f'استخدام الذاكرة مرتفع: {memory_usage:.2f} MB',
                'timestamp': datetime.now().isoformat()
            })

        # تحذيرات معدل النجاح
        if self.stats['total_pages'] > 0:
            success_rate = (self.stats['processed_pages'] / self.stats['total_pages']) * 100
            if success_rate < 90:
                warnings.append({
                    'type': 'success_rate_warning',
                    'message': f'معدل نجاح المعالجة منخفض: {success_rate:.2f}%',
                    'timestamp': datetime.now().isoformat()
                })

        return warnings

    def reset(self):
        """إعادة تعيين المعالج للاستخدام مجدداً"""
        try:
            # تنظيف الموارد الحالية
            self.cleanup()
            
            # إعادة تهيئة المتغيرات
            self.temp_dir = tempfile.mkdtemp()
            self.current_pdf_path = None
            self.writer = PdfWriter()
            self.current_pdf = None
            self.modified_pages = set()
            
            # إعادة تعيين الإحصائيات
            self.stats = {
                'processed_pages': 0,
                'translated_blocks': 0,
                'skipped_pages': 0,
                'total_pages': 0,
                'start_time': None,
                'end_time': None,
                'errors': []
            }
            
            self.logger.info("تم إعادة تعيين المعالج بنجاح")
            
        except Exception as e:
            self.logger.error(f"خطأ في إعادة تعيين المعالج: {str(e)}")
            raise

    @property
    def is_busy(self) -> bool:
        """التحقق من حالة المعالج"""
        return self.current_pdf_path is not None

class PDFTranslator:
    def __init__(self, text_processor=None, page_processor=None, pdf_handler=None):
        self.text_processor = text_processor
        self.page_processor = page_processor
        self.pdf_handler = pdf_handler
        self._processing_lock = False
        self._current_page = None
        self._processed_pages = set()
        self._current_pdf = None
        self._temp_files = []
        
        # تهيئة الإحصائيات
        self.stats = {
            'processed_pages': 0,
            'translated_blocks': 0,
            'chess_notations': 0,
            'diagrams': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
        
        # أنماط تدوين الشطرنج
        self.chess_patterns = {
            'moves': r'[KQRBN]?[a-h][1-8]',
            'captures': r'x',
            'castling': r'O-O(?:-O)?',
            'check': r'\+',
            'mate': r'#'
        }

    def initialize_processing(self):
        """تهيئة عملية المعالجة"""
        self.stats['start_time'] = datetime.now()
        self._temp_files.clear()
        self._processed_pages.clear()
        self._current_page = None
        self._current_pdf = None
        self.stats.update({
            'processed_pages': 0,
            'translated_blocks': 0,
            'chess_notations': 0,
            'diagrams': 0,
            'errors': []
        })

    def translate_pdf(self, input_path: str, output_path: str) -> bool:
        """ترجمة ومعالجة ملف PDF"""
        if self._processing_lock:
            logging.warning("هناك عملية معالجة جارية")
            return False

        self._processing_lock = True
        self.initialize_processing()

        try:
            logging.info(f"بدء معالجة الملف: {input_path}")
            
            # التحقق من وجود الملف
            if not Path(input_path).exists():
                raise FileNotFoundError(f"الملف غير موجود: {input_path}")

            with pdfplumber.open(input_path) as pdf:
                self._current_pdf = pdf
                total_pages = len(pdf.pages)
                
                with tqdm(total=total_pages, desc="تقدم المعالجة") as pbar:
                    for page_num in range(total_pages):
                        if page_num not in self._processed_pages:
                            if self.process_page(page_num):
                                self._processed_pages.add(page_num)
                                self.stats['processed_pages'] += 1
                                pbar.update(1)
                            else:
                                logging.warning(f"فشل في معالجة الصفحة {page_num + 1}")

            # حفظ الملف النهائي
            if self.stats['processed_pages'] > 0:
                success = self.pdf_handler.save_pdf(output_path)
                if success:
                    logging.info(f"تم حفظ الملف بنجاح: {output_path}")
                return success

            return False

        except Exception as e:
            logging.error(f"خطأ في معالجة الملف: {str(e)}")
            self.stats['errors'].append({
                'type': 'file_processing',
                'error': str(e)
            })
            return False

        finally:
            self._processing_lock = False
            self.cleanup()
            self.stats['end_time'] = datetime.now()

    def process_page(self, page_num: int) -> bool:
        """معالجة صفحة واحدة من الملف"""
        if self._current_page == page_num or not self._current_pdf:
            return False

        self._current_page = page_num
        try:
            logging.info(f"معالجة صفحة {page_num + 1}")
            page = self._current_pdf.pages[page_num]

            # استخراج النص
            text = page.extract_text()
            if not text:
                return False

            # معالجة النص
            processed_text = self.text_processor.process_text(text)
            if processed_text:
                self.stats['translated_blocks'] += 1
                self.page_processor.process_page(processed_text, page_num)

            # معالجة تدوينات الشطرنج
            self.process_chess_content(text, page)

            return True

        except Exception as e:
            self.handle_error(page_num, e)
            return False

        finally:
            self._current_page = None

    def process_chess_content(self, text: str, page) -> None:
        """معالجة محتوى الشطرنج في الصفحة"""
        # استخراج تدوينات الشطرنج
        notations = self.extract_chess_notations(text)
        if notations:
            self.stats['chess_notations'] += len(notations)

        # البحث عن مخططات الشطرنج
        if self.detect_chess_diagram(page):
            self.stats['diagrams'] += 1

    def extract_chess_notations(self, text: str) -> list:
        """استخراج تدوينات الشطرنج من النص"""
        notations = []
        for name, pattern in self.chess_patterns.items():
            matches = re.finditer(pattern, text)
            notations.extend(match.group() for match in matches)
        return notations

    def detect_chess_diagram(self, page) -> bool:
        """اكتشاف وجود مخطط شطرنج في الصفحة"""
        try:
            tables = page.extract_tables()
            for table in tables:
                if len(table) == 8 and all(len(row) == 8 for row in table):
                    return True
            return False
        except Exception as e:
            logging.warning(f"خطأ في اكتشاف مخطط الشطرنج: {e}")
            return False

    def handle_error(self, page_num: int, error: Exception) -> None:
        """معالجة الأخطاء"""
        error_info = {
            'page': page_num + 1,
            'error': str(error),
            'type': type(error).__name__
        }
        self.stats['errors'].append(error_info)
        logging.error(f"خطأ في معالجة الصفحة {page_num + 1}: {error}")

    def cleanup(self) -> None:
        """تنظيف الموارد المؤقتة"""
        for temp_file in self._temp_files:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception as e:
                logging.warning(f"خطأ في حذف الملف المؤقت {temp_file}: {e}")
        self._temp_files.clear()

    def get_statistics(self) -> dict:
        """الحصول على إحصائيات المعالجة"""
        return self.stats

    def __del__(self):
        """المنظف - يتم استدعاؤه عند حذف الكائن"""
        self.cleanup()

class PDFTextProcessor:
    """معالجة النصوص في ملفات PDF"""
    
    def __init__(self, config_manager: ConfigManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.text_blocks = []
        self.current_page = 0
        self.total_pages = 0
        self.processed_count = 0
        self.error_count = 0
        self.stats = defaultdict(int)

    def process_page_text(self, page_text: str, page_number: int) -> List[Dict[str, Any]]:
        """معالجة نص الصفحة واستخراج العناصر"""
        processed_elements = []
        try:
            # تقسيم النص إلى أقسام
            sections = self._split_text_into_sections(page_text)
            
            for section in sections:
                # تحليل كل قسم
                elements = self._analyze_text_section(section, page_number)
                if elements:
                    processed_elements.extend(elements)
                    
                # تحديث الإحصائيات
                self.stats['processed_sections'] += 1
                
        except Exception as e:
            self.logger.error(f"خطأ في معالجة نص الصفحة {page_number}: {e}")
            self.error_count += 1
            
        return processed_elements

    def _split_text_into_sections(self, text: str) -> List[str]:
        """تقسيم النص إلى أقسام منطقية"""
        sections = []
        try:
            # تنظيف النص
            text = self._clean_text(text)
            
            # تقسيم حسب الفقرات
            paragraphs = text.split('\n\n')
            
            for para in paragraphs:
                if para.strip():
                    # تقسيم الفقرات الطويلة
                    if len(para) > 500:
                        sub_sections = self._split_long_paragraph(para)
                        sections.extend(sub_sections)
                    else:
                        sections.append(para.strip())
                        
        except Exception as e:
            self.logger.error(f"خطأ في تقسيم النص: {e}")
            
        return sections

    def _clean_text(self, text: str) -> str:
        """تنظيف النص من العناصر غير المرغوب فيها"""
        try:
            # إزالة الفراغات الزائدة
            text = re.sub(r'\s+', ' ', text)
            
            # إزالة الرموز الخاصة
            text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\{\}\'\"\،\؛\؟]', '', text)
            
            # تنظيف علامات الترقيم
            text = re.sub(r'[\.\,\!\?\;\:\-]{2,}', '.', text)
            
            # تنظيف الأقواس الفارغة
            text = re.sub(r'\(\s*\)|\[\s*\]|\{\s*\}', '', text)
            
            return text.strip()
            
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف النص: {e}")
            return text

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """تقسيم الفقرات الطويلة إلى أجزاء أصغر"""
        sections = []
        try:
            # تقسيم حسب الجمل
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            
            current_section = []
            current_length = 0
            
            for sentence in sentences:
                sentence_length = len(sentence)
                
                if current_length + sentence_length > 500:
                    # حفظ القسم الحالي
                    if current_section:
                        sections.append(' '.join(current_section))
                    # بدء قسم جديد
                    current_section = [sentence]
                    current_length = sentence_length
                else:
                    current_section.append(sentence)
                    current_length += sentence_length
            
            # إضافة القسم الأخير
            if current_section:
                sections.append(' '.join(current_section))
                
        except Exception as e:
            self.logger.error(f"خطأ في تقسيم الفقرة: {e}")
            sections.append(paragraph)
            
        return sections

    def _analyze_text_section(self, section: str, page_number: int) -> List[Dict[str, Any]]:
        """تحليل قسم النص واستخراج العناصر"""
        elements = []
        try:
            # تحليل النص
            text_type = self._determine_text_type(section)
            direction = self._determine_text_direction(section)
            language = self._detect_language(section)
            
            # إنشاء عنصر النص
            text_element = {
                'text': section,
                'type': text_type,
                'direction': direction,
                'language': language,
                'page': page_number,
                'length': len(section),
                'word_count': len(section.split()),
                'processed_time': datetime.utcnow().isoformat()
            }
            
            elements.append(text_element)
            
            # تحديث الإحصائيات
            self.stats['processed_elements'] += 1
            self.stats[f'type_{text_type}'] += 1
            self.stats[f'lang_{language}'] += 1
            
        except Exception as e:
            self.logger.error(f"خطأ في تحليل قسم النص: {e}")
            
        return elements

    def _determine_text_type(self, text: str) -> str:
        """تحديد نوع النص"""
        if not text.strip():
            return 'empty'
            
        # التحقق من العناوين
        if text.isupper() or text.istitle():
            return 'header'
            
        # التحقق من القوائم
        if re.match(r'^\s*[\-\*\•\d]+\.?\s', text):
            return 'list_item'
            
        # التحقق من الجداول
        if '\t' in text or '    ' in text:
            return 'table_content'
            
        # التحقق من الأرقام
        if text.replace('.', '').isdigit():
            return 'number'
            
        return 'paragraph'

    def _determine_text_direction(self, text: str) -> str:
        """تحديد اتجاه النص"""
        # التحقق من وجود حروف عربية
        arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
        if arabic_pattern.search(text):
            return 'rtl'
            
        return 'ltr'

    def _detect_language(self, text: str) -> str:
        """اكتشاف لغة النص"""
        try:
            # التحقق من وجود حروف عربية
            if re.search(r'[\u0600-\u06FF]', text):
                return 'ar'
                
            # التحقق من وجود حروف إنجليزية
            if re.search(r'[a-zA-Z]', text):
                return 'en'
                
            # التحقق من وجود أرقام فقط
            if text.replace('.', '').isdigit():
                return 'numeric'
                
            return 'unknown'
            
        except Exception as e:
            self.logger.error(f"خطأ في اكتشاف اللغة: {e}")
            return 'unknown'

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات المعالجة"""
        return {
            'total_pages': self.total_pages,
            'processed_pages': self.current_page,
            'error_count': self.error_count,
            'processed_elements': self.stats['processed_elements'],
            'processed_sections': self.stats['processed_sections'],
            'text_types': {
                k: v for k, v in self.stats.items()
                if k.startswith('type_')
            },
            'languages': {
                k: v for k, v in self.stats.items()
                if k.startswith('lang_')
            }
        }
    
class ChessNotationProcessor:
    """معالجة تدوين الشطرنج في النصوص"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.chess_pieces = {
            'K': 'الملك',
            'Q': 'الوزير',
            'R': 'الرخ',
            'B': 'الفيل',
            'N': 'الحصان',
            'P': 'جندي',
            'king': 'الملك',
            'queen': 'الوزير',
            'rook': 'الرخ',
            'bishop': 'الفيل',
            'knight': 'الحصان',
            'pawn': 'جندي'
        }
        self.chess_terms = {
            'check': 'كش',
            'checkmate': 'كش مات',
            'stalemate': 'تعادل',
            'draw': 'تعادل',
            'castling': 'تبييت',
            'promotion': 'ترقية',
            'captures': 'يأسر',
            'x': 'يأسر',
            'en passant': 'أخذ في المرور'
        }
        
    def process_chess_notation(self, text: str) -> str:
        """معالجة تدوين الشطرنج وترجمته"""
        try:
            # معالجة الحركات الخاصة
            text = self._process_special_moves(text)
            
            # معالجة قطع الشطرنج
            text = self._process_chess_pieces(text)
            
            # معالجة المصطلحات
            text = self._process_chess_terms(text)
            
            return text
            
        except Exception as e:
            self.logger.error(f"خطأ في معالجة تدوين الشطرنج: {e}")
            return text

    def _process_special_moves(self, text: str) -> str:
        """معالجة الحركات الخاصة في الشطرنج"""
        try:
            # التبييت القصير
            text = re.sub(r'O-O(?!-O)', 'تبييت قصير', text)
            
            # التبييت الطويل
            text = re.sub(r'O-O-O', 'تبييت طويل', text)
            
            # الأسر
            text = re.sub(r'(\w+)x(\w+)', r'\1 يأسر \2', text)
            
            return text
            
        except Exception as e:
            self.logger.error(f"خطأ في معالجة الحركات الخاصة: {e}")
            return text

    def _process_chess_pieces(self, text: str) -> str:
        """معالجة أسماء قطع الشطرنج"""
        try:
            for eng, arab in self.chess_pieces.items():
                text = re.sub(rf'\b{eng}\b', arab, text)
            return text
        except Exception as e:
            self.logger.error(f"خطأ في معالجة قطع الشطرنج: {e}")
            return text

    def _process_chess_terms(self, text: str) -> str:
        """معالجة مصطلحات الشطرنج"""
        try:
            for eng, arab in self.chess_terms.items():
                text = re.sub(rf'\b{eng}\b', arab, text)
            return text
        except Exception as e:
            self.logger.error(f"خطأ في معالجة مصطلحات الشطرنج: {e}")
            return text
        

class PDFRenderer:
    """معالج عرض وتنسيق PDF"""
    
    def __init__(self, config_manager: ConfigManager, font_manager: FontManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.font_manager = font_manager
        self.chess_processor = ChessNotationProcessor()
        self.current_page = 0
        self.total_pages = 0
        self.page_size = A4
        self.margins = {
            'top': 50,
            'bottom': 50,
            'left': 50,
            'right': 50
        }

    def create_page(self, canvas_obj, elements: List[Dict[str, Any]]) -> None:
        """إنشاء صفحة جديدة في PDF"""
        try:
            # إعداد الصفحة
            self._setup_page(canvas_obj)
            
            # معالجة العناصر
            y_position = self.page_size[1] - self.margins['top']
            for element in elements:
                y_position = self._render_element(canvas_obj, element, y_position)
                
                # التحقق من الحاجة لصفحة جديدة
                if y_position < self.margins['bottom']:
                    canvas_obj.showPage()
                    self._setup_page(canvas_obj)
                    y_position = self.page_size[1] - self.margins['top']
                    
        except Exception as e:
            self.logger.error(f"خطأ في إنشاء الصفحة: {e}")

    def _setup_page(self, canvas_obj) -> None:
        """إعداد الصفحة الجديدة"""
        try:
            # تعيين الخط
            arabic_font = self.font_manager.get_arabic_font()
            if arabic_font:
                font_name = f"Arabic_{Path(arabic_font).stem}"
                canvas_obj.setFont(font_name, 12)
                
            # إضافة ترويسة الصفحة
            self._add_header(canvas_obj)
            
            # إضافة تذييل الصفحة
            self._add_footer(canvas_obj)
            
        except Exception as e:
            self.logger.error(f"خطأ في إعداد الصفحة: {e}")

    def _render_element(self, canvas_obj, element: Dict[str, Any], y_position: float) -> float:
        """عرض عنصر على الصفحة"""
        try:
            text = element['text']
            
            # معالجة تدوين الشطرنج إذا وجد
            if self._contains_chess_notation(text):
                text = self.chess_processor.process_chess_notation(text)
            
            # معالجة النص العربي
            if element['direction'] == 'rtl':
                text = get_display(arabic_reshaper.reshape(text))
            
            # حساب موضع النص
            text_width = canvas_obj.stringWidth(text)
            x_position = self._calculate_x_position(text_width, element['direction'])
            
            # رسم النص
            canvas_obj.drawString(x_position, y_position, text)
            
            # تحديث الموضع العمودي
            return y_position - 20
            
        except Exception as e:
            self.logger.error(f"خطأ في عرض العنصر: {e}")
            return y_position - 20

    def _contains_chess_notation(self, text: str) -> bool:
        """التحقق من وجود تدوين شطرنج"""
        chess_patterns = [
            r'O-O(?!-O)',  # التبييت القصير
            r'O-O-O',      # التبييت الطويل
            r'[KQRBN][a-h][1-8]',  # حركات القطع
            r'[a-h]x[a-h][1-8]',    # الأسر
            r'\+',         # الكش
            r'\#'          # الكش مات
        ]
        
        return any(re.search(pattern, text) for pattern in chess_patterns)

    def _calculate_x_position(self, text_width: float, direction: str) -> float:
        """حساب الموضع الأفقي للنص"""
        if direction == 'rtl':
            return self.page_size[0] - self.margins['right'] - text_width
        return self.margins['left']

    def _add_header(self, canvas_obj) -> None:
        """إضافة ترويسة الصفحة"""
        try:
            # معلومات الترجمة
            header_text = f"ترجمة PDF - الصفحة {self.current_page}/{self.total_pages}"
            header_text = get_display(arabic_reshaper.reshape(header_text))
            
            canvas_obj.drawString(
                self.margins['left'],
                self.page_size[1] - 30,
                header_text
            )
        except Exception as e:
            self.logger.error(f"خطأ في إضافة الترويسة: {e}")

    def _add_footer(self, canvas_obj) -> None:
        """إضافة تذييل الصفحة"""
        try:
            # معلومات المعالجة
            footer_text = f"تمت المعالجة في {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            footer_text = get_display(arabic_reshaper.reshape(footer_text))
            
            canvas_obj.drawString(
                self.margins['left'],
                self.margins['bottom'] - 20,
                footer_text
            )
        except Exception as e:
            self.logger.error(f"خطأ في إضافة التذييل: {e}")
    
    def cleanup_temp_files(self):
        """تنظيف الملفات المؤقتة"""
        try:
            temp_dir = Path(__file__).parent / 'temp'
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                temp_dir.mkdir()
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف الملفات المؤقتة: {e}")


class PDFSecurityHandler:
    """معالج أمان وتشفير ملفات PDF"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.temp_dir = Path(__file__).parent / 'temp' / 'security'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._setup_security()

    def _setup_security(self):
        """إعداد معايير الأمان"""
        self.security_options = {
            'owner_pwd': None,  # كلمة مرور المالك
            'user_pwd': None,   # كلمة مرور المستخدم
            'use_128bit': True  # استخدام تشفير 128 بت
        }

    def secure_pdf(self, input_path: str, output_path: str, owner_pwd: str = None, user_pwd: str = None) -> bool:
        """تأمين ملف PDF"""
        try:
            reader = PdfReader(input_path)
            writer = PdfWriter()

            # نسخ جميع الصفحات
            for page in reader.pages:
                writer.add_page(page)

            # إضافة التشفير
            if owner_pwd or user_pwd:
                writer.encrypt(
                    user_password=user_pwd or "",
                    owner_password=owner_pwd or user_pwd or "",
                    use_128bit=self.security_options['use_128bit']
                )

            # حفظ الملف المشفر
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)

            return True

        except Exception as e:
            self.logger.error(f"خطأ في تأمين الملف: {e}")
            return False

class PDFMetadataProcessor:
    """معالج البيانات الوصفية لملفات PDF"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.metadata_fields = [
            'Title', 'Author', 'Subject', 'Keywords',
            'Creator', 'Producer', 'CreationDate', 'ModDate'
        ]

    def update_metadata(self, pdf_path: str, metadata: Dict[str, str]) -> bool:
        """تحديث البيانات الوصفية للملف"""
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()

            # نسخ الصفحات
            for page in reader.pages:
                writer.add_page(page)

            # تحديث البيانات الوصفية
            writer.add_metadata({
                f"/{k}": v for k, v in metadata.items()
                if k in self.metadata_fields
            })

            # حفظ التغييرات
            temp_path = f"{pdf_path}.temp"
            with open(temp_path, 'wb') as output_file:
                writer.write(output_file)

            # استبدال الملف الأصلي
            shutil.move(temp_path, pdf_path)
            return True

        except Exception as e:
            self.logger.error(f"خطأ في تحديث البيانات الوصفية: {e}")
            return False
        

class OCRProcessor:
    """معالج التعرف الضوئي على النصوص"""
    
    def __init__(self, config_manager: ConfigManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.tesseract_config = {
            'lang': 'ara+eng',
            'config': '--psm 3',
            'timeout': 30
        }
        self.image_types = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp'}
        self.dpi = 300
        self.temp_dir = Path(__file__).parent / 'temp' / 'ocr'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.stats = defaultdict(int)

    def process_image(self, image_path: str) -> str:
        """معالجة صورة واحدة"""
        try:
            # التحقق من نوع الملف
            if not self._is_valid_image(image_path):
                raise ValueError(f"نوع ملف غير مدعوم: {image_path}")

            # تحميل وتحسين الصورة
            img = self._preprocess_image(image_path)
            if img is None:
                return ""

            # التعرف على النص
            text = pytesseract.image_to_string(
                img,
                lang=self.tesseract_config['lang'],
                config=self.tesseract_config['config']
            )

            self.stats['processed_images'] += 1
            return text.strip()

        except Exception as e:
            self.logger.error(f"خطأ في معالجة الصورة {image_path}: {e}")
            self.stats['failed_images'] += 1
            return ""

    def process_pdf_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """معالجة صور PDF"""
        results = []
        try:
            # تحويل PDF إلى صور
            images = convert_from_path(
                pdf_path,
                dpi=self.dpi,
                output_folder=str(self.temp_dir)
            )

            # معالجة كل صورة
            for i, img in enumerate(images, 1):
                temp_path = self.temp_dir / f"page_{i}.png"
                img.save(str(temp_path), 'PNG')

                # التعرف على النص
                text = self.process_image(str(temp_path))
                if text:
                    results.append({
                        'page': i,
                        'text': text,
                        'image_path': str(temp_path),
                        'timestamp': datetime.now().isoformat()
                    })

            return results

        except Exception as e:
            self.logger.error(f"خطأ في معالجة صور PDF: {e}")
            return results

        finally:
            self._cleanup_temp_files()

    def _is_valid_image(self, image_path: str) -> bool:
        """التحقق من صلاحية الصورة"""
        return Path(image_path).suffix.lower() in self.image_types

    def _preprocess_image(self, image_path: str) -> Optional[Image.Image]:
        """تحسين الصورة قبل المعالجة"""
        try:
            img = Image.open(image_path)

            # تحويل إلى تدرج الرمادي
            if img.mode != 'L':
                img = img.convert('L')

            # تحسين التباين
            img = ImageEnhance.Contrast(img).enhance(2.0)

            # تنعيم الصورة
            img = img.filter(ImageFilter.MedianFilter(size=3))

            return img

        except Exception as e:
            self.logger.error(f"خطأ في تحسين الصورة: {e}")
            return None

    def _cleanup_temp_files(self):
        """تنظيف الملفات المؤقتة"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.temp_dir.mkdir()
        except Exception as e:
            self.logger.error(f"خطأ في تنظيف الملفات المؤقتة: {e}")

    def get_statistics(self) -> Dict[str, int]:
        """الحصول على إحصائيات المعالجة"""
        return dict(self.stats)
    

class TextLayoutAnalyzer:
    """محلل تخطيط النص"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.direction_cache = {}
        self.layout_stats = defaultdict(int)

    def analyze_layout(self, page_elements: List[Dict]) -> Dict[str, Any]:
        """تحليل تخطيط الصفحة"""
        try:
            layout_info = {
                'text_direction': self._determine_main_direction(page_elements),
                'columns': self._detect_columns(page_elements),
                'paragraphs': self._group_paragraphs(page_elements),
                'headers': self._detect_headers(page_elements),
                'font_stats': self._analyze_fonts(page_elements)
            }

            self._update_statistics(layout_info)
            return layout_info

        except Exception as e:
            self.logger.error(f"خطأ في تحليل التخطيط: {e}")
            return {}

    def _determine_main_direction(self, elements: List[Dict]) -> str:
        """تحديد الاتجاه الرئيسي للنص"""
        rtl_count = ltr_count = 0

        for element in elements:
            text = element.get('text', '')
            if not text:
                continue

            # استخدام الذاكرة المؤقتة
            if text in self.direction_cache:
                direction = self.direction_cache[text]
            else:
                direction = self._detect_text_direction(text)
                self.direction_cache[text] = direction

            if direction == 'rtl':
                rtl_count += 1
            else:
                ltr_count += 1

        return 'rtl' if rtl_count > ltr_count else 'ltr'

    def _detect_text_direction(self, text: str) -> str:
        """اكتشاف اتجاه النص"""
        # التحقق من وجود حروف عربية
        arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
        if arabic_pattern.search(text):
            return 'rtl'
        return 'ltr'

    def _detect_columns(self, elements: List[Dict]) -> List[Dict[str, Any]]:
        """اكتشاف الأعمدة في الصفحة"""
        columns = []
        try:
            # تجميع العناصر حسب المواقع الأفقية
            x_positions = defaultdict(list)
            for element in elements:
                bbox = element.get('bbox', [0, 0, 0, 0])
                x_center = (bbox[0] + bbox[2]) / 2
                x_positions[int(x_center // 50) * 50].append(element)

            # تحليل الأعمدة
            for x_pos, column_elements in x_positions.items():
                if len(column_elements) > 2:  # تجاهل الأعمدة القصيرة
                    columns.append({
                        'x_position': x_pos,
                        'elements_count': len(column_elements),
                        'width': self._calculate_column_width(column_elements)
                    })

        except Exception as e:
            self.logger.error(f"خطأ في اكتشاف الأعمدة: {e}")

        return columns

    def _calculate_column_width(self, elements: List[Dict]) -> float:
        """حساب عرض العمود"""
        try:
            widths = [
                element['bbox'][2] - element['bbox'][0]
                for element in elements
                if 'bbox' in element
            ]
            return sum(widths) / len(widths) if widths else 0
        except Exception:
            return 0

    def _group_paragraphs(self, elements: List[Dict]) -> List[Dict[str, Any]]:
        """تجميع العناصر في فقرات"""
        paragraphs = []
        current_paragraph = []
        last_y = None
        line_spacing = 0

        try:
            # ترتيب العناصر من أعلى إلى أسفل
            sorted_elements = sorted(
                elements,
                key=lambda x: (-x.get('bbox', [0, 0, 0, 0])[1])
            )

            for element in sorted_elements:
                bbox = element.get('bbox', [0, 0, 0, 0])
                current_y = bbox[1]

                if last_y is None:
                    last_y = current_y
                    current_paragraph.append(element)
                    continue

                # حساب المسافة بين السطور
                spacing = abs(current_y - last_y)
                if line_spacing == 0:
                    line_spacing = spacing

                # تحديد إذا كان العنصر جزءاً من نفس الفقرة
                if spacing <= line_spacing * 1.5:
                    current_paragraph.append(element)
                else:
                    if current_paragraph:
                        paragraphs.append({
                            'elements': current_paragraph,
                            'bbox': self._calculate_paragraph_bbox(current_paragraph),
                            'text': self._extract_paragraph_text(current_paragraph)
                        })
                    current_paragraph = [element]

                last_y = current_y

            # إضافة الفقرة الأخيرة
            if current_paragraph:
                paragraphs.append({
                    'elements': current_paragraph,
                    'bbox': self._calculate_paragraph_bbox(current_paragraph),
                    'text': self._extract_paragraph_text(current_paragraph)
                })

        except Exception as e:
            self.logger.error(f"خطأ في تجميع الفقرات: {e}")

        return paragraphs

    def _detect_headers(self, elements: List[Dict]) -> List[Dict[str, Any]]:
        """اكتشاف العناوين في النص"""
        headers = []
        try:
            for element in elements:
                if self._is_header(element):
                    headers.append({
                        'text': element.get('text', ''),
                        'bbox': element.get('bbox', []),
                        'level': self._determine_header_level(element)
                    })
        except Exception as e:
            self.logger.error(f"خطأ في اكتشاف العناوين: {e}")
        return headers

    def _is_header(self, element: Dict) -> bool:
        """التحقق مما إذا كان العنصر عنواناً"""
        text = element.get('text', '')
        if not text:
            return False

        # التحقق من خصائص العنوان
        return any([
            text.isupper(),
            len(text.split()) <= 10 and text[0].isupper(),
            element.get('font', {}).get('size', 0) > 12,
            element.get('bold', False)
        ])

    def _determine_header_level(self, element: Dict) -> int:
        """تحديد مستوى العنوان"""
        font_size = element.get('font', {}).get('size', 0)
        if font_size > 18:
            return 1
        elif font_size > 14:
            return 2
        return 3

    def _analyze_fonts(self, elements: List[Dict]) -> Dict[str, Any]:
        """تحليل الخطوط المستخدمة"""
        font_stats = defaultdict(lambda: {
            'count': 0,
            'sizes': set(),
            'styles': set()
        })

        try:
            for element in elements:
                font = element.get('font', {})
                font_name = font.get('name', 'unknown')
                font_size = font.get('size', 0)
                font_style = font.get('style', 'normal')

                font_stats[font_name]['count'] += 1
                font_stats[font_name]['sizes'].add(font_size)
                font_stats[font_name]['styles'].add(font_style)

            # تحويل المجموعات إلى قوائم للتسلسل JSON
            for font_name in font_stats:
                font_stats[font_name]['sizes'] = sorted(font_stats[font_name]['sizes'])
                font_stats[font_name]['styles'] = sorted(font_stats[font_name]['styles'])

        except Exception as e:
            self.logger.error(f"خطأ في تحليل الخطوط: {e}")

        return dict(font_stats)

    def _calculate_paragraph_bbox(self, elements: List[Dict]) -> List[float]:
        """حساب الإطار المحيط للفقرة"""
        try:
            x0 = min(e['bbox'][0] for e in elements)
            y0 = min(e['bbox'][1] for e in elements)
            x1 = max(e['bbox'][2] for e in elements)
            y1 = max(e['bbox'][3] for e in elements)
            return [x0, y0, x1, y1]
        except Exception:
            return [0, 0, 0, 0]

    def _extract_paragraph_text(self, elements: List[Dict]) -> str:
        """استخراج النص الكامل للفقرة"""
        try:
            return ' '.join(e.get('text', '') for e in elements)
        except Exception:
            return ''

    def _update_statistics(self, layout_info: Dict[str, Any]):
        """تحديث إحصائيات التخطيط"""
        try:
            self.layout_stats['total_paragraphs'] += len(layout_info.get('paragraphs', []))
            self.layout_stats['total_headers'] += len(layout_info.get('headers', []))
            self.layout_stats['total_columns'] += len(layout_info.get('columns', []))
            
            direction = layout_info.get('text_direction', 'ltr')
            self.layout_stats[f'direction_{direction}'] += 1

        except Exception as e:
            self.logger.error(f"خطأ في تحديث الإحصائيات: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التحليل"""
        return dict(self.layout_stats)
    # إضافة معالجة النهاية والتنظيف
    def cleanup_all():
        """تنظيف جميع الملفات المؤقتة والموارد"""
        try:
            temp_dirs = [
                'temp', 'cache', 'images', 'ocr',
                'security', 'output', 'logs'
            ]
            base_path = Path(__file__).parent
            
            for dir_name in temp_dirs:
                dir_path = base_path / dir_name
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    dir_path.mkdir(exist_ok=True)
                    
            logging.info("تم تنظيف جميع الملفات المؤقتة")
        except Exception as e:
            logging.error(f"خطأ في تنظيف الملفات: {e}")

   
        # تسجيل دالة التنظيف ليتم تنفيذها عند إغلاق البرنامج
    atexit.register(cleanup_all)


class PDFOptimizer:
    """محسن ملفات PDF"""
    
    def __init__(self, config_manager: ConfigManager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.optimization_options = {
            'compress_images': True,
            'optimize_fonts': True,
            'remove_metadata': False,
            'linearize': True
        }
        
    def optimize_pdf(self, input_path: str, output_path: str) -> bool:
        """تحسين ملف PDF"""
        try:
            # قراءة الملف الأصلي
            reader = PdfReader(input_path)
            writer = PdfWriter()
            
            # نسخ الصفحات مع التحسين
            for page in reader.pages:
                writer.add_page(page)
            
            # تطبيق خيارات التحسين
            if self.optimization_options['compress_images']:
                self._compress_images(writer)
            
            if self.optimization_options['optimize_fonts']:
                self._optimize_fonts(writer)
            
            if self.optimization_options['remove_metadata']:
                writer.add_metadata({})
            
            # حفظ الملف المحسن
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            if self.optimization_options['linearize']:
                self._linearize_pdf(output_path)
            
            return True
            
        except Exception as e:
            self.logger.error(f"خطأ في تحسين الملف: {e}")
            return False
            
    def _compress_images(self, writer: PdfWriter):
        """ضغط الصور"""
        try:
            for page in writer.pages:
                for image in page.images:
                    if image.size > 100000:  # تجاهل الصور الصغيرة
                        image.compress_jpeg()
        except Exception as e:
            self.logger.error(f"خطأ في ضغط الصور: {e}")
            
    def _optimize_fonts(self, writer: PdfWriter):
        """تحسين الخطوط"""
        try:
            # تحديد الخطوط المستخدمة
            used_fonts = set()
            for page in writer.pages:
                for font in page.fonts:
                    used_fonts.add(font.name)
            
            # إزالة الخطوط غير المستخدمة
            writer.remove_unused_fonts()
            
        except Exception as e:
            self.logger.error(f"خطأ في تحسين الخطوط: {e}")
            
    def _linearize_pdf(self, pdf_path: str):
        """تحسين تدفق الملف"""
        try:
            # استخدام QPDF لتحسين التدفق
            temp_path = f"{pdf_path}.temp"
            subprocess.run([
                'qpdf', '--linearize',
                pdf_path, temp_path
            ], check=True)
            
            # استبدال الملف الأصلي
            shutil.move(temp_path, pdf_path)
            
        except Exception as e:
            self.logger.error(f"خطأ في تحسين تدفق الملف: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)       


    
    
    def parse_arguments():
        """تحليل معاملات سطر الأوامر"""
        parser = argparse.ArgumentParser(description='معالج ترجمة ملفات PDF')
        parser.add_argument('input', help='مسار ملف PDF المدخل', nargs='?')
        parser.add_argument('-o', '--output', help='مسار ملف PDF المخرج')
        parser.add_argument('-d', '--debug', action='store_true', help='تفعيل وضع التصحيح')
        return parser.parse_args()

    def setup_logging(debug_mode: bool):
        """إعداد التسجيل"""
        level = logging.DEBUG if debug_mode else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )        

    

    def main():
        try:
            print("\n=== PDF Translator ===")
            print(f"Version: {SYSTEM_CONFIG['version']}")
            print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"User: {SYSTEM_CONFIG['user']}")
            print("=====================\n")

            # تهيئة التسجيل
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )

            # تهيئة المكونات
            config = ConfigManager()
            text_processor = TextProcessor()
            arabic_handler = ArabicTextHandler()
            text_processor.arabic_handler = arabic_handler
            page_processor = PageProcessor(text_processor)
            pdf_handler = PDFHandler(config, page_processor)

            # تجهيز المترجم - تعديل هنا فقط
            translator = PDFTranslator(
                text_processor=text_processor,
                page_processor=page_processor,
                pdf_handler=pdf_handler
            )
            
            # تحديد المسارات
            base_dir = Path(SYSTEM_CONFIG['base_dir'])
            input_dir = base_dir / "input"
            output_dir = base_dir / "output"
            
            # إنشاء المجلدات إذا لم تكن موجودة
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            # المسار الافتراضي للملف
            default_input = input_dir / "document.pdf"
            
            # معالجة معاملات سطر الأوامر
            parser = argparse.ArgumentParser(description='PDF Translator')
            parser.add_argument('input', help='Input PDF file', nargs='?', 
                              default=str(default_input))
            parser.add_argument('-o', '--output', help='Output PDF file')
            parser.add_argument('-d', '--debug', action='store_true', 
                              help='Enable debug mode')
            args = parser.parse_args()

            if args.debug:
                logging.getLogger().setLevel(logging.DEBUG)

            # تحديد ملف المدخلات
            input_file = Path(args.input)
            
            # التحقق من وجود الملف
            if not input_file.exists():
                print(f"خطأ: الملف غير موجود: {input_file}")
                return 1

            if not input_file.is_file() or input_file.suffix.lower() != '.pdf':
                print(f"خطأ: يجب أن يكون الملف بصيغة PDF: {input_file}")
                return 1

            # تحديد ملف المخرجات
            if args.output:
                output_file = Path(args.output)
            else:
                output_file = output_dir / f"translated_{input_file.stem}.pdf"

            # عرض معلومات المعالجة
            print("\nمعلومات المعالجة:")
            print(f"المجلد الرئيسي: {base_dir}")
            print(f"مجلد المدخلات: {input_dir}")
            print(f"مجلد المخرجات: {output_dir}")
            print(f"الملف المصدر: {input_file}")
            print(f"حجم الملف: {input_file.stat().st_size / (1024*1024):.2f} MB")
            print(f"الملف الناتج: {output_file}")

            # بدء المعالجة
            print("\nجاري بدء المعالجة...")
            start_time = time.time()

            try:
                # تعديل هنا فقط - تغيير اسم الدالة
                result = translator.translate_pdf(
                    str(input_file),
                    str(output_file)
                )

                if not result:
                    print("\nفشل في معالجة الملف")
                    return 1

            except KeyboardInterrupt:
                print("\nتم إيقاف البرنامج بواسطة المستخدم")
                return 130
            except Exception as e:
                print(f"\nخطأ في المعالجة: {e}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                return 1

            # عرض الإحصائيات
            duration = time.time() - start_time
            stats = translator.get_statistics()
            
            print("\nإحصائيات المعالجة:")
            print(f"وقت المعالجة: {duration:.2f} ثانية")
            print(f"عدد الصفحات: {stats['processed_pages']}")
            print(f"الكتل المترجمة: {stats['translated_blocks']}")
            
            if stats['errors']:
                print(f"\nعدد الأخطاء: {len(stats['errors'])}")
                if args.debug:
                    for error in stats['errors']:
                        print(f"- صفحة {error['page']}: {error['error']}")

            print(f"\nتم حفظ الملف المترجم في:")
            print(output_file)
            
            return 0

        except Exception as e:
            print(f"\nخطأ غير متوقع: {e}")
            if args.debug:
                import traceback
                traceback.print_exc()
            return 1

    if __name__ == "__main__":
        sys.exit(main())

