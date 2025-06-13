#!/usr/bin/env python3
"""
カード生成機能のテストスクリプト
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
    
    # テスト画像1: カラフルな画像
    img1 = Image.new('RGB', (400, 300))
    draw1 = ImageDraw.Draw(img1)
    for i in range(0, 400, 20):
        color = (i % 255, (i * 2) % 255, (i * 3) % 255)
        draw1.rectangle([i, 0, i + 20, 300], fill=color)
    img1.save(os.path.join(test_dir, "colorful.jpg"))
    
    # テスト画像2: シンプルな画像
    img2 = Image.new('RGB', (400, 300), color=(100, 150, 200))
    draw2 = ImageDraw.Draw(img2)
    draw2.ellipse([100, 75, 300, 225], fill=(255, 255, 255))
    img2.save(os.path.join(test_dir, "simple.jpg"))
    
    # テスト画像3: 複雑な画像
    img3 = Image.new('RGB', (400, 300))
    draw3 = ImageDraw.Draw(img3)
    # ランダムな線を描画
    np.random.seed(42)
    for _ in range(100):
        x1, y1 = np.random.randint(0, 400), np.random.randint(0, 300)
        x2, y2 = np.random.randint(0, 400), np.random.randint(0, 300)
        color = tuple(np.random.randint(0, 256, 3))
        draw3.line([x1, y1, x2, y2], fill=color, width=2)
    img3.save(os.path.join(test_dir, "complex.jpg"))
    
    print("テスト画像を生成しました:")
    print("- test_images/colorful.jpg")
    print("- test_images/simple.jpg") 
    print("- test_images/complex.jpg")

def test_card_generation():
    """
    カード生成機能をテスト
    """
    print("\n=== カード生成テスト ===")
    
    try:
        from card_generator import CardGenerator
        
        # テスト画像が存在しない場合は作成
        if not os.path.exists("test_images"):
            create_test_images()
        
        generator = CardGenerator()
        
        test_images = [
            "test_images/colorful.jpg",
            "test_images/simple.jpg",
            "test_images/complex.jpg"
        ]
        
        # 存在するファイルのみをテスト
        existing_images = [img for img in test_images if os.path.exists(img)]
        
        if not existing_images:
            print("テスト画像が見つかりません。先にcreate_test_images()を実行してください。")
            return False
        
        print(f"{len(existing_images)}枚の画像でテストを実行...")
        
        # カードを生成
        cards_info = generator.generate_cards_batch(existing_images, "test_output")
        
        if cards_info:
            print(f"\n✓ {len(cards_info)}枚のカードが正常に生成されました！")
            
            for card in cards_info:
                print(f"  - {card['name']}: パワー {card['power']}")
                print(f"    特徴量: {json.dumps(card['features'], indent=4)}")
            
            # 結果をJSONで保存
            with open("test_output/test_results.json", "w", encoding="utf-8") as f:
                json.dump(cards_info, f, ensure_ascii=False, indent=2)
            
            return True
        else:
            print("✗ カードの生成に失敗しました")
            return False
            
    except ImportError as e:
        print(f"✗ インポートエラー: {e}")
        print("必要なライブラリがインストールされているか確認してください")
        return False
    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        return False

def test_api_server():
    """
    APIサーバーのテスト（サーバーが起動している場合）
    """
    print("\n=== API サーバーテスト ===")
    
    try:
        # ヘルスチェック
        response = requests.get('http://localhost:5000/health', timeout=5)
        if response.status_code == 200:
            print("✓ サーバーが正常に動作しています")
            print(f"  レスポンス: {response.json()}")
            return True
        else:
            print(f"✗ サーバーエラー: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ サーバーに接続できません")
        print("  APIサーバーが起動していることを確認してください")
        print("  起動コマンド: python api_interface.py")
        return False
    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        return False

def main():
    """
    メインテスト関数
    """
    print("画像処理・カード生成機能のテストを開始します...\n")
    
    # 1. テスト画像の生成
    if not os.path.exists("test_images"):
        print("=== テスト画像生成 ===")
        create_test_images()
    
    # 2. カード生成テスト
    card_test_result = test_card_generation()
    
    # 3. APIサーバーテスト
    api_test_result = test_api_server()
    
    # 結果のまとめ
    print("\n" + "="*50)
    print("テスト結果:")
    print(f"  カード生成: {'✓ 成功' if card_test_result else '✗ 失敗'}")
    print(f"  APIサーバー: {'✓ 成功' if api_test_result else '✗ 失敗'}")
    
    if card_test_result:
        print("\n生成されたファイル:")
        print("  - test_output/ (カード画像)")
        print("  - test_output/test_results.json (詳細情報)")
    
    print("\n次のステップ:")
    print("1. git add . && git commit -m 'feat: 画像処理・カード生成機能を実装'")
    print("2. git push origin feature/image-processing")
    print("3. GitHubでプルリクエストを作成")

if __name__ == "__main__":
    main()