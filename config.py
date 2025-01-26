#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Text Processor Module
Created: 2025-01-23 17:14:43
Author: x9ci
"""

from googletrans import Translator
import re
import logging
import time
from typing import List
from arabic_handler import ArabicHandler

class TextProcessor:
    def __init__(self):
        self.translator = Translator()
        self.batch_size = 10
        self.arabic_handler = ArabicHandler()

    def clean_text(self, text: str) -> str:
        """تنظيف النص من الأحرف غير المرغوب فيها"""
        text = re.sub(r'^\d+$', '', text)
        text = re.sub(r'[^\w\s\-.,?!]', ' ', text)
        text = ' '.join(text.split())
        return text.strip()

    def is_chess_notation(self, text: str) -> bool:
        """التحقق مما إذا كان النص تدوين شطرنج"""
        patterns = [
            r'^[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](\+|#)?$',
            r'^O-O(-O)?$',
            r'^[0-1](/[0-1])?-[0-1](/[0-1])?$',
            r'\d{1,4}\.',
            r'½-½',
        ]
        return any(bool(re.match(pattern, text.strip())) for pattern in patterns)

    def process_text_batch(self, texts: List[str]) -> List[str]:
        """معالجة مجموعة من النصوص"""
        translated_texts = []
        
        print(f"معالجة دفعة من {len(texts)} نص")
        
        for text in texts:
            try:
                if not text or len(text.strip()) < 3:
                    translated_texts.append("")
                    continue
                    
                # ترجمة النص
                translated = self.translator.translate(text, src='en', dest='ar').text
                
                # معالجة النص العربي
                processed_text = self.arabic_handler.process_text(translated)
                translated_texts.append(processed_text)
                
                print(f"النص الأصلي: {text}")
                print(f"الترجمة: {processed_text}")
                
                time.sleep(0.5)  # تأخير لتجنب التقييد
                
            except Exception as e:
                print(f"خطأ في ترجمة النص: {str(e)}")
                translated_texts.append("")
        
        return translated_texts