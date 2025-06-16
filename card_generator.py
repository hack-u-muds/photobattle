import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import json
from typing import List, Tuple, Dict
import random
from enum import Enum

class CardAttribute(Enum):
    """
    カードの属性
    """
    FIRE = "火"      # 赤系、暖色、高エネルギー
    WATER = "水"     # 青系、寒色、冷静
    EARTH = "土"     # 緑・茶系、自然、安定

class CardGenerator:
    """
    写真からカードを生成するクラス
    """
    
    def __init__(self, card_width: int = 300, card_height: int = 420):
        self.card_width = card_width
        self.card_height = card_height
        self.image_width = 260
        self.image_height = 180
        
        # カードテンプレートの設定
        self.bg_color = (255, 255, 255)  # 白背景
        self.border_color = (0, 0, 0)    # 黒枠
        self.text_color = (0, 0, 0)      # 黒文字
        
        # 属性色の設定
        self.attribute_colors = {
            CardAttribute.FIRE: (220, 50, 50),   # 赤
            CardAttribute.WATER: (50, 100, 220), # 青
            CardAttribute.EARTH: (50, 150, 50)   # 緑
        }
        
        # 属性相性表 (攻撃側 -> 防御側 -> 倍率)
        self.attribute_effectiveness = {
            CardAttribute.FIRE: {
                CardAttribute.FIRE: 1.0,    # 等倍
                CardAttribute.WATER: 0.8,   # 不利
                CardAttribute.EARTH: 1.2    # 有利
            },
            CardAttribute.WATER: {
                CardAttribute.FIRE: 1.2,    # 有利
                CardAttribute.WATER: 1.0,   # 等倍
                CardAttribute.EARTH: 0.8    # 不利
            },
            CardAttribute.EARTH: {
                CardAttribute.FIRE: 0.8,    # 不利
                CardAttribute.WATER: 1.2,   # 有利
                CardAttribute.EARTH: 1.0    # 等倍
            }
        }
        
    def analyze_image_features(self, image_path: str) -> Dict:
        """
        画像の特徴を分析して攻撃力と属性を算出
        """
        # 画像を読み込み
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"画像を読み込めませんでした: {image_path}")
        
        # 画像の特徴量を計算
        features = {}
        
        # BGR to HSV変換
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # 1. 色の多様性（色相の分散）
        hue_std = np.std(hsv[:, :, 0])
        features['color_diversity'] = min(hue_std / 50.0, 1.0)
        
        # 2. エッジの密度（複雑さ）
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        features['complexity'] = min(edge_density * 10, 1.0)
        
        # 3. 明度の分散（コントラスト）
        brightness_std = np.std(gray)
        features['contrast'] = min(brightness_std / 100.0, 1.0)
        
        # 4. 彩度の平均
        saturation_mean = np.mean(hsv[:, :, 1])
        features['saturation'] = saturation_mean / 255.0
        
        # 5. 画像サイズ（解像度）
        total_pixels = img.shape[0] * img.shape[1]
        features['resolution'] = min(total_pixels / 1000000.0, 1.0)
        
        # 6. 色相分析（属性決定用）
        hue_values = hsv[:, :, 0].flatten()
        features['dominant_hue'] = np.mean(hue_values)
        features['hue_distribution'] = self._analyze_hue_distribution(hue_values)
        
        # 7. 温度感（暖色・寒色）
        features['warmth'] = self._calculate_warmth(hsv)
        
        return features
    
    def _analyze_hue_distribution(self, hue_values: np.ndarray) -> Dict:
        """
        色相の分布を分析
        """
        # 色相を3つの範囲に分割
        red_range = np.sum((hue_values < 30) | (hue_values > 150))  # 赤系
        blue_range = np.sum((hue_values >= 90) & (hue_values <= 130))  # 青系
        green_range = np.sum((hue_values >= 30) & (hue_values <= 90))  # 緑系
        
        total = len(hue_values)
        
        return {
            'red_ratio': red_range / total,
            'blue_ratio': blue_range / total,
            'green_ratio': green_range / total
        }
    
    def _calculate_warmth(self, hsv: np.ndarray) -> float:
        """
        画像の温度感を計算（0.0=寒色, 1.0=暖色）
        """
        hue = hsv[:, :, 0]
        saturation = hsv[:, :, 1]
        
        # 暖色（赤・オレンジ・黄）の範囲
        warm_mask = ((hue < 30) | (hue > 150)) & (saturation > 50)
        # 寒色（青・青緑）の範囲
        cool_mask = ((hue >= 90) & (hue <= 130)) & (saturation > 50)
        
        warm_pixels = np.sum(warm_mask)
        cool_pixels = np.sum(cool_mask)
        
        if warm_pixels + cool_pixels == 0:
            return 0.5  # 中性
        
        return warm_pixels / (warm_pixels + cool_pixels)
    
    def determine_attribute(self, features: Dict) -> CardAttribute:
        """
        画像特徴から属性を決定
        """
        hue_dist = features['hue_distribution']
        warmth = features['warmth']
        saturation = features['saturation']
        
        # 属性スコアを計算
        fire_score = (
            hue_dist['red_ratio'] * 2.0 +
            warmth * 1.5 +
            saturation * 1.0 +
            features['complexity'] * 0.5
        )
        
        water_score = (
            hue_dist['blue_ratio'] * 2.0 +
            (1.0 - warmth) * 1.5 +
            features['contrast'] * 1.0 +
            (1.0 - features['complexity']) * 0.5
        )
        
        earth_score = (
            hue_dist['green_ratio'] * 2.0 +
            (1.0 - saturation) * 1.0 +
            features['resolution'] * 0.5 +
            features['color_diversity'] * 0.5
        )
        
        # 最高スコアの属性を選択
        scores = {
            CardAttribute.FIRE: fire_score,
            CardAttribute.WATER: water_score,
            CardAttribute.EARTH: earth_score
        }
        
        return max(scores.keys(), key=lambda x: scores[x])
    
    def calculate_attack_power(self, features: Dict) -> int:
        """
        特徴量から攻撃力を算出（10-100）
        """
        # 重み付き合計で攻撃力を計算
        weights = {
            'color_diversity': 0.25,
            'complexity': 0.3,
            'contrast': 0.2,
            'saturation': 0.15,
            'resolution': 0.1
        }
        
        power_score = sum(features[key] * weights[key] for key in weights)
        
        # 10-100の範囲にスケール
        attack_power = int(power_score * 80) + 15 + random.randint(-5, 5)
        return max(10, min(100, attack_power))
    
    def calculate_effective_attack_power(self, attacker_attribute: CardAttribute, 
                                       defender_attribute: CardAttribute, 
                                       base_attack: int) -> int:
        """
        属性相性を考慮した実効攻撃力を計算
        """
        multiplier = self.attribute_effectiveness[attacker_attribute][defender_attribute]
        return int(base_attack * multiplier)
    
    def resize_image_for_card(self, image_path: str) -> Image.Image:
        """
        カード用に画像をリサイズ
        """
        img = Image.open(image_path)
        
        # アスペクト比を保持してリサイズ
        img.thumbnail((self.image_width, self.image_height), Image.Resampling.LANCZOS)
        
        # 中央配置用の背景を作成
        background = Image.new('RGB', (self.image_width, self.image_height), (240, 240, 240))
        
        # 中央に配置
        x = (self.image_width - img.width) // 2
        y = (self.image_height - img.height) // 2
        background.paste(img, (x, y))
        
        return background
    
    def create_card_template(self, attribute: CardAttribute) -> Image.Image:
        """
        カードのテンプレートを作成
        """
        card = Image.new('RGB', (self.card_width, self.card_height), self.bg_color)
        draw = ImageDraw.Draw(card)
        
        # 属性色で外枠を描画
        attribute_color = self.attribute_colors[attribute]
        draw.rectangle([0, 0, self.card_width-1, self.card_height-1], 
                      outline=attribute_color, width=4)
        
        # 属性色のヘッダー部分
        draw.rectangle([4, 4, self.card_width-5, 30], fill=attribute_color)
        
        # 画像エリアの枠を描画
        img_x = (self.card_width - self.image_width) // 2
        img_y = 40
        draw.rectangle([img_x-2, img_y-2, img_x+self.image_width+2, img_y+self.image_height+2], 
                      outline=self.border_color, width=2)
        
        return card
    
    def add_text_to_card(self, card: Image.Image, attack_power: int, 
                        attribute: CardAttribute, image_name: str) -> Image.Image:
        """
        カードにテキストを追加
        """
        draw = ImageDraw.Draw(card)
        
        try:
            # macOS用のフォント設定（日本語対応）
            font_paths = [
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc", 
                "/Library/Fonts/Arial Unicode MS.ttf",
                "/System/Library/Fonts/Arial.ttf",
                "Arial.ttf"
            ]
            
            font_large = None
            font_medium = None
            font_small = None
            font_tiny = None
            
            # 利用可能なフォントを順番に試す
            for font_path in font_paths:
                try:
                    if os.path.exists(font_path):
                        font_large = ImageFont.truetype(font_path, 32)
                        font_medium = ImageFont.truetype(font_path, 20)
                        font_small = ImageFont.truetype(font_path, 16)
                        font_tiny = ImageFont.truetype(font_path, 12)
                        break
                except:
                    continue
            
            # フォントが見つからない場合はデフォルトフォントを使用
            if font_large is None:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_tiny = ImageFont.load_default()
                
        except Exception as e:
            print(f"フォント読み込みエラー: {e}")
            # デフォルトフォントを使用
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_tiny = ImageFont.load_default()
        
        # 属性名をヘッダーに表示（英語で代用）
        attribute_text = f"Type: {attribute.name}"  # 日本語の代わりに英語を使用
        draw.text((10, 8), attribute_text, fill=(255, 255, 255), font=font_small)
        
        # 攻撃力を表示（英語）
        attack_text = f"POWER: {attack_power}"
        attack_bbox = draw.textbbox((0, 0), attack_text, font=font_large)
        attack_width = attack_bbox[2] - attack_bbox[0]
        attack_x = (self.card_width - attack_width) // 2
        attack_y = 240
        draw.text((attack_x, attack_y), attack_text, fill=self.text_color, font=font_large)
        
        # 画像名を表示
        name_text = os.path.splitext(image_name)[0][:12]  # 12文字まで
        name_bbox = draw.textbbox((0, 0), name_text, font=font_medium)
        name_width = name_bbox[2] - name_bbox[0]
        name_x = (self.card_width - name_width) // 2
        name_y = 285
        draw.text((name_x, name_y), name_text, fill=self.text_color, font=font_medium)
        
        # カードタイプを表示
        type_text = "PHOTO CARD"
        type_bbox = draw.textbbox((0, 0), type_text, font=font_small)
        type_width = type_bbox[2] - type_bbox[0]
        type_x = (self.card_width - type_width) // 2
        type_y = 315
        draw.text((type_x, type_y), type_text, fill=self.text_color, font=font_small)
        
        # 属性相性説明を表示（英語）
        effectiveness_text = self._get_effectiveness_text_en(attribute)
        draw.text((10, 350), effectiveness_text, fill=self.text_color, font=font_tiny)
        
        return card
    
    def _get_effectiveness_text_en(self, attribute: CardAttribute) -> str:
        """
        属性相性の説明テキストを生成（英語版）
        """
        if attribute == CardAttribute.FIRE:
            return "FIRE > EARTH > WATER > FIRE"
        elif attribute == CardAttribute.WATER:
            return "WATER > FIRE > EARTH > WATER"
        else:  # EARTH
            return "EARTH > WATER > FIRE > EARTH"
    
    def generate_card(self, image_path: str, output_path: str) -> Dict:
        """
        1枚のカードを生成
        """
        # 画像の特徴を分析
        features = self.analyze_image_features(image_path)
        
        # 属性を決定
        attribute = self.determine_attribute(features)
        
        # 攻撃力を計算
        attack_power = self.calculate_attack_power(features)
        
        # カードテンプレートを作成
        card = self.create_card_template(attribute)
        
        # 画像をリサイズしてカードに配置
        resized_image = self.resize_image_for_card(image_path)
        img_x = (self.card_width - self.image_width) // 2
        img_y = 40
        card.paste(resized_image, (img_x, img_y))
        
        # テキストを追加
        image_name = os.path.basename(image_path)
        card = self.add_text_to_card(card, attack_power, attribute, image_name)
        
        # カードを保存
        card.save(output_path)
        
        # 属性相性を文字列キーの辞書に変換（JSON serializable）
        safe_effectiveness = {}
        for target_attr, multiplier in self.attribute_effectiveness[attribute].items():
            safe_effectiveness[target_attr.value] = multiplier
        
        # カード情報を返す（JSON serializable）
        return {
            'image_path': image_path,
            'card_path': output_path,
            'attack_power': attack_power,
            'attribute': attribute.value,  # Enumの値を文字列として取得
            'attribute_info': self.get_attribute_info(attribute),
            'features': features,
            'name': os.path.splitext(image_name)[0],
            # ゲームロジック担当者向けの生データ
            'game_data': {
                'id': None,  # ゲームロジック側で設定
                'attack_power': attack_power,
                'attribute': attribute.value,  # 文字列として保存
                'attribute_en': attribute.name.lower(),
                'effectiveness_multipliers': safe_effectiveness,  # 文字列キーの辞書
                'used': False,  # 初期状態は未使用
                'card_image_url': None  # API側で設定
            }
        }
    
    def generate_cards_batch(self, image_paths: List[str], output_dir: str) -> List[Dict]:
        """
        複数のカードを一括生成
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        cards_info = []
        
        for i, image_path in enumerate(image_paths):
            try:
                output_filename = f"card_{i+1}.png"
                output_path = os.path.join(output_dir, output_filename)
                
                card_info = self.generate_card(image_path, output_path)
                cards_info.append(card_info)
                
                print(f"カード生成完了: {output_filename} (攻撃力: {card_info['attack_power']}, 属性: {card_info['attribute']})")
                
            except Exception as e:
                print(f"エラー: {image_path} の処理中にエラーが発生しました: {e}")
                continue
        
        return cards_info
    
    def get_attribute_info(self, attribute: CardAttribute) -> Dict:
        """
        属性の詳細情報を取得（ゲームロジック担当者向け）
        """
        # 属性相性を文字列キーの辞書に変換
        effectiveness_dict = {}
        for target, multiplier in self.attribute_effectiveness[attribute].items():
            effectiveness_dict[target.value] = multiplier
        
        return {
            'name': attribute.value,
            'name_en': attribute.name.lower(),
            'color': self.attribute_colors[attribute],
            'effectiveness': effectiveness_dict
        }


# 使用例とテスト用の関数
def main():
    """
    テスト用のメイン関数
    """
    generator = CardGenerator()
    
    # テスト用の画像パス
    test_images = [
        "test_images/fire_image.jpg",
        "test_images/water_image.jpg", 
        "test_images/earth_image.jpg"
    ]
    
    # 存在する画像ファイルのみを使用
    existing_images = [img for img in test_images if os.path.exists(img)]
    
    if len(existing_images) == 0:
        print("テスト画像が見つかりません。test_card_generator.py を実行してください。")
        return
    
    # カードを生成
    cards_info = generator.generate_cards_batch(existing_images, "generated_cards")
    
    # 結果をJSONファイルに保存
    with open("generated_cards/cards_info.json", "w", encoding="utf-8") as f:
        json.dump(cards_info, f, ensure_ascii=False, indent=2)
    
    print(f"\n{len(cards_info)}枚のカードが生成されました！")
    for card in cards_info:
        print(f"- {card['name']}: 攻撃力 {card['attack_power']}, 属性 {card['attribute']}")
    
    print("\n✅ JSON serialization test passed!")


if __name__ == "__main__":
    main()