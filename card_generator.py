import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import json
from typing import List, Tuple, Dict
import random

class CardGenerator:
    """
    写真からカードを生成するクラス
    """
    
    def __init__(self, card_width: int = 300, card_height: int = 400):
        self.card_width = card_width
        self.card_height = card_height
        self.image_width = 260
        self.image_height = 200
        
        # カードテンプレートの設定
        self.bg_color = (255, 255, 255)  # 白背景
        self.border_color = (0, 0, 0)    # 黒枠
        self.text_color = (0, 0, 0)      # 黒文字
        
    def analyze_image_features(self, image_path: str) -> Dict:
        """
        画像の特徴を分析してパワー値を算出
        """
        # 画像を読み込み
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"画像を読み込めませんでした: {image_path}")
        
        # 画像の特徴量を計算
        features = {}
        
        # 1. 色の多様性（色相の分散）
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
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
        features['resolution'] = min(total_pixels / 1000000.0, 1.0)  # 100万画素で正規化
        
        return features
    
    def calculate_power(self, features: Dict) -> int:
        """
        特徴量からパワー値を算出（1-100）
        """
        # 重み付き合計でパワーを計算
        weights = {
            'color_diversity': 0.25,
            'complexity': 0.3,
            'contrast': 0.2,
            'saturation': 0.15,
            'resolution': 0.1
        }
        
        power_score = sum(features[key] * weights[key] for key in weights)
        
        # 1-100の範囲にスケール
        power = int(power_score * 80) + 10 + random.randint(-5, 5)
        return max(1, min(100, power))
    
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
    
    def create_card_template(self) -> Image.Image:
        """
        カードのテンプレートを作成
        """
        card = Image.new('RGB', (self.card_width, self.card_height), self.bg_color)
        draw = ImageDraw.Draw(card)
        
        # 外枠を描画
        draw.rectangle([0, 0, self.card_width-1, self.card_height-1], 
                      outline=self.border_color, width=3)
        
        # 画像エリアの枠を描画
        img_x = (self.card_width - self.image_width) // 2
        img_y = 20
        draw.rectangle([img_x-2, img_y-2, img_x+self.image_width+2, img_y+self.image_height+2], 
                      outline=self.border_color, width=2)
        
        return card
    
    def add_text_to_card(self, card: Image.Image, power: int, image_name: str) -> Image.Image:
        """
        カードにテキストを追加
        """
        draw = ImageDraw.Draw(card)
        
        try:
            # フォントを設定（システムフォントを使用）
            font_large = ImageFont.truetype("Arial.ttf", 36)
            font_medium = ImageFont.truetype("Arial.ttf", 24)
            font_small = ImageFont.truetype("Arial.ttf", 16)
        except:
            # フォントが見つからない場合はデフォルトフォントを使用
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # パワー値を表示
        power_text = f"POWER: {power}"
        power_bbox = draw.textbbox((0, 0), power_text, font=font_large)
        power_width = power_bbox[2] - power_bbox[0]
        power_x = (self.card_width - power_width) // 2
        power_y = 250
        draw.text((power_x, power_y), power_text, fill=self.text_color, font=font_large)
        
        # 画像名を表示
        name_text = os.path.splitext(image_name)[0][:15]  # 15文字まで
        name_bbox = draw.textbbox((0, 0), name_text, font=font_medium)
        name_width = name_bbox[2] - name_bbox[0]
        name_x = (self.card_width - name_width) // 2
        name_y = 300
        draw.text((name_x, name_y), name_text, fill=self.text_color, font=font_medium)
        
        # カードタイプを表示
        type_text = "PHOTO CARD"
        type_bbox = draw.textbbox((0, 0), type_text, font=font_small)
        type_width = type_bbox[2] - type_bbox[0]
        type_x = (self.card_width - type_width) // 2
        type_y = 340
        draw.text((type_x, type_y), type_text, fill=self.text_color, font=font_small)
        
        return card
    
    def generate_card(self, image_path: str, output_path: str) -> Dict:
        """
        1枚のカードを生成
        """
        # 画像の特徴を分析
        features = self.analyze_image_features(image_path)
        
        # パワー値を計算
        power = self.calculate_power(features)
        
        # カードテンプレートを作成
        card = self.create_card_template()
        
        # 画像をリサイズしてカードに配置
        resized_image = self.resize_image_for_card(image_path)
        img_x = (self.card_width - self.image_width) // 2
        img_y = 20
        card.paste(resized_image, (img_x, img_y))
        
        # テキストを追加
        image_name = os.path.basename(image_path)
        card = self.add_text_to_card(card, power, image_name)
        
        # カードを保存
        card.save(output_path)
        
        # カード情報を返す
        return {
            'image_path': image_path,
            'card_path': output_path,
            'power': power,
            'features': features,
            'name': os.path.splitext(image_name)[0]
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
                
                print(f"カード生成完了: {output_filename} (パワー: {card_info['power']})")
                
            except Exception as e:
                print(f"エラー: {image_path} の処理中にエラーが発生しました: {e}")
                continue
        
        return cards_info


# 使用例とテスト用の関数
def main():
    """
    テスト用のメイン関数
    """
    generator = CardGenerator()
    
    # テスト用の画像パス（実際のパスに変更してください）
    test_images = [
        "test_images/image1.jpg",
        "test_images/image2.jpg", 
        "test_images/image3.jpg"
    ]
    
    # カードを生成
    cards_info = generator.generate_cards_batch(test_images, "generated_cards")
    
    # 結果をJSONファイルに保存
    with open("generated_cards/cards_info.json", "w", encoding="utf-8") as f:
        json.dump(cards_info, f, ensure_ascii=False, indent=2)
    
    print(f"\n{len(cards_info)}枚のカードが生成されました！")
    for card in cards_info:
        print(f"- {card['name']}: パワー {card['power']}")


if __name__ == "__main__":
    main()