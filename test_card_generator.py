#!/usr/bin/env python3
"""
カード生成機能のテストスクリプト（完全版・修正済み）
"""

import os
import sys
import json
import requests
from PIL import Image, ImageDraw
import numpy as np

def create_test_images():
    """
    テスト用の画像を生成
    """
    test_dir = "test_images"
    os.makedirs(test_dir, exist_ok=True)
    
    print("テスト画像生成中...")
    
    try:
        # 火属性画像（赤系・複雑）
        img1 = Image.new('RGB', (300, 300))
        draw1 = ImageDraw.Draw(img1)
        draw1.rectangle([0, 0, 300, 300], fill=(200, 50, 50))
        for i in range(10):
            x = i * 30
            y = i * 30
            draw1.rectangle([x, y, x+20, y+20], fill=(255, 100, 0))
            draw1.ellipse([x+10, y+10, x+25, y+25], fill=(255, 200, 0))
        np.random.seed(1)
        for _ in range(20):
            x1, y1 = np.random.randint(0, 300), np.random.randint(0, 300)
            x2, y2 = np.random.randint(0, 300), np.random.randint(0, 300)
            draw1.line([x1, y1, x2, y2], fill=(255, 150, 0), width=2)
        img1.save(os.path.join(test_dir, "fire_image.jpg"))
        
        # 水属性画像（青系・シンプル）
        img2 = Image.new('RGB', (300, 300))
        draw2 = ImageDraw.Draw(img2)
        draw2.rectangle([0, 0, 300, 300], fill=(50, 100, 200))
        for y in range(0, 300, 40):
            for x in range(0, 300, 30):
                wave_offset = int(15 * np.sin(x * 0.02))
                draw2.ellipse([x, y + wave_offset, x+20, y + wave_offset + 20], 
                             fill=(100, 150, 255))
        img2.save(os.path.join(test_dir, "water_image.jpg"))
        
        # 土属性画像（緑・茶系・中程度）
        img3 = Image.new('RGB', (300, 300))
        draw3 = ImageDraw.Draw(img3)
        draw3.rectangle([0, 0, 300, 300], fill=(139, 90, 60))
        np.random.seed(2)
        for _ in range(15):
            x = np.random.randint(0, 250)
            y = np.random.randint(0, 250)
            draw3.ellipse([x, y, x+30, y+30], fill=(50, 150, 50))
            draw3.line([x+15, y+15, x+15, y+45], fill=(101, 67, 33), width=3)
        img3.save(os.path.join(test_dir, "earth_image.jpg"))
        
        print("✅ テスト画像生成完了")
        return True
        
    except Exception as e:
        print(f"❌ 複雑な画像生成失敗: {e}")
        print("シンプルな画像で再試行...")
        
        try:
            img1 = Image.new('RGB', (200, 200), color=(255, 0, 0))
            draw1 = ImageDraw.Draw(img1)
            draw1.rectangle([50, 50, 150, 150], fill=(255, 100, 0))
            img1.save(os.path.join(test_dir, "fire_image.jpg"))
            
            img2 = Image.new('RGB', (200, 200), color=(0, 0, 255))
            draw2 = ImageDraw.Draw(img2)
            draw2.ellipse([50, 50, 150, 150], fill=(0, 200, 255))
            img2.save(os.path.join(test_dir, "water_image.jpg"))
            
            img3 = Image.new('RGB', (200, 200), color=(0, 150, 0))
            draw3 = ImageDraw.Draw(img3)
            draw3.polygon([(100, 50), (150, 150), (50, 150)], fill=(100, 200, 100))
            img3.save(os.path.join(test_dir, "earth_image.jpg"))
            
            print("✅ シンプルなテスト画像生成完了")
            return True
            
        except Exception as e2:
            print(f"❌ シンプル画像生成も失敗: {e2}")
            return False

def test_card_generation():
    """
    カード生成機能をテスト
    """
    print("カード生成テスト実行中...")
    
    try:
        from card_generator import CardGenerator
        
        generator = CardGenerator()
        
        test_images = [
            "test_images/fire_image.jpg",
            "test_images/water_image.jpg",
            "test_images/earth_image.jpg"
        ]
        
        missing_files = [img for img in test_images if not os.path.exists(img)]
        if missing_files:
            print(f"不足している画像: {missing_files}")
            print("テスト画像を生成します...")
            if not create_test_images():
                print("❌ テスト画像生成に失敗")
                return False
        
        existing_images = [img for img in test_images if os.path.exists(img)]
        
        if len(existing_images) == 0:
            print("❌ テスト画像が1枚も見つかりません")
            return False
        
        print(f"📁 {len(existing_images)}枚の画像でテスト実行")
        
        os.makedirs("test_output", exist_ok=True)
        
        cards_info = generator.generate_cards_batch(existing_images, "test_output")
        
        if cards_info and len(cards_info) > 0:
            print("✅ カード生成成功")
            for card in cards_info:
                attr_en = card['attribute_info']['name_en'].upper()
                print(f"  - {card['name']}: POWER {card['attack_power']}, TYPE {attr_en}")
            return True
        else:
            print("❌ カード生成失敗 - 生成されたカードが0枚")
            return False
            
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        print("card_generator.py が存在することを確認してください")
        return False
    except Exception as e:
        print(f"❌ カード生成エラー: {e}")
        import traceback
        print("詳細エラー:")
        traceback.print_exc()
        return False

def test_api_server():
    """
    APIサーバーのテスト
    """
    print("APIサーバーテスト実行中...")
    
    try:
        response = requests.get('http://localhost:5000/health', timeout=5)
        if response.status_code == 200:
            print("✅ APIサーバー動作確認")
            return True
        else:
            print(f"❌ サーバーエラー: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ サーバー接続エラー")
        print("  → python api_interface.py でサーバーを起動してください")
        return False
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

def main():
    """
    メインテスト関数
    """
    print("🎨 Card Generation Test Start\n")
    
    os.makedirs("test_images", exist_ok=True)
    os.makedirs("test_output", exist_ok=True)
    
    print("=== Test Image Preparation ===")
    image_created = create_test_images()
    if not image_created:
        print("❌ テスト画像の生成に失敗しました")
        return
    
    print("\n=== Card Generation Test ===")
    card_test_result = test_card_generation()
    
    print("\n=== API Server Test ===")
    api_test_result = test_api_server()
    
    print("\n" + "="*40)
    print("📊 Test Results:")
    print(f"  Test Images: {'✅ Success' if image_created else '❌ Failed'}")
    print(f"  Card Generation: {'✅ Success' if card_test_result else '❌ Failed'}")
    print(f"  API Server: {'✅ Success' if api_test_result else '❌ Failed'}")
    
    if card_test_result:
        print("\n📁 生成ファイル:")
        print("  - test_output/ (カード画像)")
        print("  - test_output/cards_for_game_logic.json (ゲームロジック用)")
        print("  - test_output/cards_detailed.json (詳細情報)")
        print("\n✨ カード生成機能が正常に動作しています!")
        print("\n🎮 カード情報:")
        
        try:
            with open("test_output/cards_for_game_logic.json", "r", encoding="utf-8") as f:
                cards_data = json.load(f)
                for i, card_data in enumerate(cards_data, 1):
                    game_data = card_data.get('game_data', {})
                    print(f"  Card {i}: {game_data.get('attack_power', 'N/A')} POWER, {game_data.get('attribute_en', 'unknown').upper()} TYPE")
        except:
            print("  (詳細情報の読み込みに失敗)")
    else:
        print("\n🔧 カード生成に問題があります。詳細なエラーを確認してください。")

if __name__ == "__main__":
    main()