from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
import uuid
from datetime import datetime
from card_generator import CardGenerator, CardAttribute
from typing import List, Dict
import shutil

app = Flask(__name__)
CORS(app)

# 設定
UPLOAD_FOLDER = 'uploads'
CARDS_FOLDER = 'generated_cards'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CARDS_FOLDER'] = CARDS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# フォルダの作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CARDS_FOLDER, exist_ok=True)

# CardGeneratorのインスタンス
card_generator = CardGenerator()

def allowed_file(filename: str) -> bool:
    """
    アップロードされたファイルが許可された拡張子かチェック
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def prepare_card_for_game_logic(card_info: Dict, session_id: str, card_index: int) -> Dict:
    """
    ゲームロジック担当者向けのカードデータを準備
    """
    game_card = card_info['game_data'].copy()
    game_card['id'] = card_index + 1
    game_card['card_image_url'] = f'/api/cards/{session_id}/card_{card_index + 1}.png'
    
    return {
        'id': game_card['id'],
        'name': card_info['name'],
        'attack_power': game_card['attack_power'],
        'attribute': game_card['attribute'],
        'attribute_en': game_card['attribute_en'],
        'card_image_url': game_card['card_image_url'],
        'used': game_card['used'],
        'effectiveness_info': {
            'strong_against': [attr for attr, mult in game_card['effectiveness_multipliers'].items() if mult > 1.0],
            'weak_against': [attr for attr, mult in game_card['effectiveness_multipliers'].items() if mult < 1.0],
            'normal_against': [attr for attr, mult in game_card['effectiveness_multipliers'].items() if mult == 1.0]
        }
    }

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    ヘルスチェック用エンドポイント
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'card-generator',
        'version': '2.0.0',
        'features': ['attribute_system', 'card_generation']
    })

@app.route('/api/cards/generate', methods=['POST'])
def generate_cards():
    """
    3枚の画像からカードを生成するメインエンドポイント
    """
    try:
        # リクエストの検証
        if 'images' not in request.files:
            return jsonify({'error': 'No images provided'}), 400
        
        files = request.files.getlist('images')
        
        if len(files) != 3:
            return jsonify({'error': 'Exactly 3 images required'}), 400
        
        # セッションIDを生成
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        cards_folder = os.path.join(app.config['CARDS_FOLDER'], session_id)
        
        os.makedirs(session_folder, exist_ok=True)
        os.makedirs(cards_folder, exist_ok=True)
        
        # ファイルを保存
        uploaded_files = []
        for i, file in enumerate(files):
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{i+1}{ext}"
                filepath = os.path.join(session_folder, filename)
                file.save(filepath)
                uploaded_files.append(filepath)
            else:
                # クリーンアップ
                shutil.rmtree(session_folder, ignore_errors=True)
                shutil.rmtree(cards_folder, ignore_errors=True)
                return jsonify({'error': f'Invalid file: {file.filename}'}), 400
        
        # カードを生成
        cards_info = card_generator.generate_cards_batch(uploaded_files, cards_folder)
        
        if len(cards_info) == 0:
            return jsonify({'error': 'Failed to generate any cards'}), 500
        
        # ゲームロジック担当者向けのデータを準備
        game_cards = []
        for i, card_info in enumerate(cards_info):
            game_card = prepare_card_for_game_logic(card_info, session_id, i)
            game_cards.append(game_card)
        
        # レスポンス用のデータを準備
        response_data = {
            'session_id': session_id,
            'cards': game_cards,
            'timestamp': datetime.now().isoformat(),
            'card_generation_info': {
                'total_cards': len(game_cards),
                'attributes_generated': [card['attribute'] for card in game_cards],
                'average_attack_power': sum(card['attack_power'] for card in game_cards) / len(game_cards)
            },
            'attribute_system': {
                'attributes': ['火', '水', '土'],
                'effectiveness_rules': 'fire > earth > water > fire'
            }
        }
        
        # セッション情報をファイルに保存
        session_data = {
            'response_data': response_data,
            'detailed_cards_info': [{k: v for k, v in card.items() if 'effectiveness_multipliers' not in str(v)} for card in cards_info]
        }
        
        session_info_path = os.path.join(cards_folder, 'session_info.json')
        with open(session_info_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/cards/<session_id>/<card_filename>', methods=['GET'])
def get_card(session_id: str, card_filename: str):
    """
    生成されたカード画像を取得
    """
    try:
        # セキュリティチェック
        card_filename = secure_filename(card_filename)
        card_path = os.path.join(app.config['CARDS_FOLDER'], session_id, card_filename)
        
        if not os.path.exists(card_path):
            return jsonify({'error': 'Card not found'}), 404
        
        return send_file(card_path, mimetype='image/png')
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving card: {str(e)}'}), 500

@app.route('/get-session-info/<session_id>', methods=['GET'])
def get_session_info(session_id: str):
    """
    セッション情報を取得
    """
    try:
        session_info_path = os.path.join(app.config['CARDS_FOLDER'], session_id, 'session_info.json')
        
        if not os.path.exists(session_info_path):
            return jsonify({'error': 'Session not found'}), 404
        
        with open(session_info_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        return jsonify(session_data['response_data'])
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving session info: {str(e)}'}), 500

@app.route('/get-card-details/<session_id>', methods=['GET'])
def get_card_details(session_id: str):
    """
    カードの詳細情報を取得（開発・デバッグ用）
    """
    try:
        session_info_path = os.path.join(app.config['CARDS_FOLDER'], session_id, 'session_info.json')
        
        if not os.path.exists(session_info_path):
            return jsonify({'error': 'Session not found'}), 404
        
        with open(session_info_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        return jsonify({
            'session_id': session_id,
            'detailed_cards': session_data['detailed_cards_info']
        })
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving card details: {str(e)}'}), 500

@app.route('/attribute-info', methods=['GET'])
def get_attribute_info():
    """
    属性システムの情報を取得
    """
    try:
        # 各属性の情報を取得
        attributes_info = {}
        for attr in CardAttribute:
            attr_info = card_generator.get_attribute_info(attr)
            attributes_info[attr.value] = {
                'name': attr_info['name'],
                'name_en': attr_info['name_en'],
                'color_rgb': attr_info['color'],
                'effectiveness': attr_info['effectiveness']
            }
        
        return jsonify({
            'attributes': attributes_info,
            'system_info': {
                'total_attributes': len(CardAttribute),
                'effectiveness_system': 'rock_paper_scissors_style',
                'damage_multipliers': {
                    'advantage': 1.2,
                    'normal': 1.0,
                    'disadvantage': 0.8
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving attribute info: {str(e)}'}), 500

@app.route('/cleanup-session/<session_id>', methods=['DELETE'])
def cleanup_session(session_id: str):
    """
    セッションのクリーンアップ
    """
    try:
        session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        cards_folder = os.path.join(app.config['CARDS_FOLDER'], session_id)
        
        cleaned_folders = []
        
        if os.path.exists(session_folder):
            shutil.rmtree(session_folder)
            cleaned_folders.append('uploads')
        
        if os.path.exists(cards_folder):
            shutil.rmtree(cards_folder)
            cleaned_folders.append('generated_cards')
        
        return jsonify({
            'message': 'Session cleaned up successfully',
            'cleaned_folders': cleaned_folders
        })
        
    except Exception as e:
        return jsonify({'error': f'Error cleaning up session: {str(e)}'}), 500

# エラーハンドラー
@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large (max 16MB)'}), 413

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Bad request'}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5001)