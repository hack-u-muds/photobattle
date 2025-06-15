#!/usr/bin/env python3
"""
カード生成機能のテストスクリプト（シンプル版）
"""

import os
import sys
import json
import requests
from PIL import Image, ImageDraw
import numpy as np

def create_test_images():
    """
    テスト用の画像を生成（属性の特徴を強調）
    """
    test_dir = "test_images"
    os.makedirs(test_dir, exist_ok=True)
    
    print("テスト画像生成中...")
    
    # テスト画像1: 火属性向け（赤・暖色系、複雑）
    img1 = Image.new('RGB', (400, 300))
    draw1 = ImageDraw.Draw(img1)
    for i in range(0, 400, 10):
        for j in range(0, 300, 10):
            red = min(255, 200 + (i // 10) % 55)
            green = min(255, 50 + (i // 15) % 100)
            blue = 30
            draw1.rectangle([i, j, i + 10, j + 10], fill=(red, green, blue))
    for _ in range(50):
        x1, y1 = np.random.randint(0, 400), np.random.randint(0, 300)
        x2, y2 = np.random.randint(0, 400), np.random.randint(0, 300)
        draw1.line([x1, y1, x2, y2], fill=(255, 100, 0), width=3)
    img1.save(os.path.join(test_dir, "fire_image.jpg"))
    
    # テスト画像2: 水属性向け（青・寒色系、シンプル）
    img2 = Image.new('RGB', (400, 300))
    draw2 = ImageDraw.Draw(img2)
    draw2.rectangle([0, 0, 400, 300], fill=(50, 150, 220))
    for y in range(0, 300, 30):
        for x in range(0, 400, 20):
            wave_height = int(10 * np.sin(x * 0.02))
            draw2.ellipse([x, y + wave_height, x + 15, y + wave_height + 15], 
                         fill=(80, 180, 255))
    img2.save(os.path.join(test_dir, "water_image.jpg"))
    
    # テスト画像3: 土属性向け（緑・茶系、中程度の複雑さ）
    img3 = Image.new('RGB', (400, 300))
    draw3 = ImageDraw.Draw(img3)
    draw3.rectangle([0, 0, 400, 300], fill=(139, 90, 60))
    np.random.seed(42)
    for _ in range(30):
        x = np.random.randint(0, 350)
        y = np.random.randint(0, 250)
        draw3.ellipse([x, y, x + 50, y + 30], fill=(34, 139, 34))
        draw3.line([x + 25, y + 15, x + 25, y + 50], fill=(101, 67, 33), width=5)
    img3.save(os.path.join(test_dir, "earth_image.jpg"))
    
    print("✅ テスト画像生成完了")

def test_card_generation():
    """
    カード生成機能をテスト
    """
    print("カード生成テスト実行中...")
    
    try:
        from card_generator import CardGenerator
        
        # テスト画像が存在しない場合は作成
        if not os.path.exists("test_images"):
            create_test_images()
        
        generator = CardGenerator()
        
        test_images = [
            "test_images/fire_image.jpg",
            "test_images/water_image.jpg",
            "test_images/earth_image.jpg"
        ]
        
        # 存在するファイルのみをテスト
        existing_images = [img for img in test_images if os.path.exists(img)]
        
        if not existing_images:
            print("❌ テスト画像が見つかりません")
            return False
        
        # カードを生成
        cards_info = generator.generate_cards_batch(existing_images, "test_output")
        
        if cards_info:
            print("✅ カード生成成功")
            for card in cards_info:
                print(f"  - {card['name']}: 攻撃力{card['attack_power']}, 属性{card['attribute']}")
            return True
        else:
            print("❌ カード生成失敗")
            return False
            
    except ImportError as e:
        print(f"❌ ライブラリエラー: {e}")
        return False
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

def test_api_server():
    """
    APIサーバーのテスト
    """
    print("APIサーバーテスト実行中...")
    
    try:
        # ヘルスチェック
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
    print("🎨 カード生成テスト開始\n")
    
    # 1. テスト画像の生成
    if not os.path.exists("test_images"):
        create_test_images()
    
    # 2. カード生成テスト
    card_test_result = test_card_generation()
    
    # 3. APIサーバーテスト
    api_test_result = test_api_server()
    
    # 結果のまとめ
    print("\n" + "="*40)
    print("📊 テスト結果:")
    print(f"  カード生成: {'✅ 成功' if card_test_result else '❌ 失敗'}")
    print(f"  APIサーバー: {'✅ 成功' if api_test_result else '❌ 失敗'}")
    
    if card_test_result:
        print("\n📁 ファイル出力完了:")
        print("  - test_output/ (カード画像)")
        print("  - cards_for_game_logic.json (ゲームロジック用)")

if __name__ == "__main__":
    main()