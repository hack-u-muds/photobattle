#!/usr/bin/env python3
"""
カード生成機能のテストスクリプト（完全版）
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
        # 背景を赤に
        draw1.rectangle([0, 0, 300, 300], fill=(200, 50, 50))
        # 複雑なパターンを追加
        for i in range(10):
            x = i * 30
            y = i * 30
            draw1.rectangle([x, y, x+20, y+20], fill=(255, 100, 0))
            draw1.ellipse([x+10, y+10, x+25, y+25], fill=(255, 200, 0))
        # ランダムな線を追加（複雑さを増加）
        np.random.seed(1)  # 固定シードで再現性確保
        for _ in range(20):
            x1, y1 = np.random.randint(0, 300), np.random.randint(0, 300)
            x2, y2 = np.random.randint(0, 300), np.random.randint(0, 300)
            draw1.line([x1, y1, x2, y2], fill=(255, 150, 0), width=2)
        img1.save(os.path.join(test_dir, "fire_image.jpg"))
        
        # 水属性画像（青系・シンプル）
        img2 = Image.new('RGB', (300, 300))
        draw2 = ImageDraw.Draw(img2)
        # 背景を青に
        draw2.rectangle([0, 0, 300, 300], fill=(50, 100, 200))
        # シンプルな波パターン
        for y in range(0, 300, 40):
            for x in range(0, 300, 30):
                wave_offset = int(15 * np.sin(x * 0.02))
                draw2.ellipse([x, y + wave_offset, x+20, y + wave_offset + 20], 
                             fill=(100, 150, 255))
        img2.save(os.path.join(test_dir, "water_image.jpg"))
        
        # 土属性画像（緑・茶系・中程度）
        img3 = Image.new('RGB', (300, 300))
        draw3 = ImageDraw.Draw(img3)
        # 背景を茶色に
        draw3.rectangle([0, 0, 300, 300], fill=(139, 90, 60))
        # 緑の要素を追加
        np.random.seed(2)  # 固定シードで再現性確保
        for _ in range(15):
            x = np.random.randint(0, 250)
            y = np.random.randint(0, 250)
            # 緑の円
            draw3.ellipse([x, y, x+30, y+30], fill=(50, 150, 50))
            # 茶色の線
            draw3.line([x+15, y+15, x+15, y+45], fill=(101, 67, 33), width=3)
        img3.save(os.path.join(test_dir, "earth_image.jpg"))
        
        print("✅ テスト画像生成完了")
        return True
        
    except Exception as e:
        print(f"❌ 複雑な画像生成失敗: {e}")
        print("シンプルな画像で再試行...")
        
        # フォールバック: 非常にシンプルな画像
        try:
            # 火属性: 赤い正方形
            img1 = Image.new('RGB', (200, 200), color=(255, 0, 0))
            draw1 = ImageDraw.Draw(img1)
            draw1.rectangle([50, 50, 150, 150], fill=(255, 100, 0))
            img1.save(os.path.join(test_dir, "fire_image.jpg"))
            
            # 水属性: 青い円
            img2 = Image.new('RGB', (200, 200), color=(0, 0, 255))
            draw2 = ImageDraw.Draw(img2)
            draw2.ellipse([50, 50, 150, 150], fill=(0, 200, 255))
            img2.save(os.path.join(test_dir, "water_image.jpg"))
            
            # 土属性: 緑の三角
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
        
        # 存在しないファイルがあるかチェック
        missing_files = [img for img in test_images if not os.path.exists(img)]
        if missing_files:
            print(f"不足している画像: {missing_files}")
            print("テスト画像を生成します...")
            if not create_test_images():
                print("❌ テスト画像生成に失敗")
                return False
        
        # 再度存在確認
        existing_images = [img for img in test_images if os.path.exists(img)]
        
        if len(existing_images) == 0:
            print("❌ テスト画像が1枚も見つかりません")
            return False
        
        print(f"📁 {len(existing_images)}枚の画像でテスト実行")
        
        # 出力ディレクトリを作成
        os.makedirs("test_output", exist_ok=True)
        
        # カードを生成
        cards_info = generator.generate_cards_batch(existing_images, "test_output")
        
        if cards_info and len(cards_info) > 0:
            print("✅ カード生成成功")
            for card in cards_info:
                print(f"  - {card['name']}: 攻撃力{card['attack_power']}, 属性{card['attribute']}")
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
        # デバッグ情報を表示
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
    print("🎨 カード生成テスト開始\n")
    
    # 1. 事前に必要なディレクトリを作成
    os.makedirs("test_images", exist_ok=True)
    os.makedirs("test_output", exist_ok=True)
    
    # 2. テスト画像を必ず生成
    print("=== テスト画像準備 ===")
    image_created = create_test_images()
    if not image_created:
        print("❌ テスト画像の生成に失敗しました")
        return
    
    # 3. カード生成テスト
    print("\n=== カード生成テスト ===")
    card_test_result = test_card_generation()
    
    # 4. APIサーバーテスト
    print("\n=== APIサーバーテスト ===")
    api_test_result = test_api_server()
    
    # 結果のまとめ
    print("\n" + "="*40)
    print("📊 テスト結果:")
    print(f"  テスト画像: {'✅ 成功' if image_created else '❌ 失敗'}")
    print(f"  カード生成: {'✅ 成功' if card_test_result else '❌ 失敗'}")
    print(f"  APIサーバー: {'✅ 成功' if api_test_result else '❌ 失敗'}")
    
    if card_test_result:
        print("\n📁 生成ファイル:")
        print("  - test_output/ (カード画像)")
        print("  - test_output/cards_for_game_logic.json (ゲームロジック用)")
        print("  - test_output/cards_detailed.json (詳細情報)")
        print("\n✨ カード生成機能が正常に動作しています!")
    else:
        print("\n🔧 カード生成に問題があります。詳細なエラーを確認してください。")

if __name__ == "__main__":
    main()