from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import json
import uuid
from datetime import datetime
from card_generator import CardGenerator
from typing import List, Dict
import tempfile
import shutil

app = Flask(__name__)

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

def cleanup_old_files():
    """
    古いファイルをクリーンアップ（オプション）
    """
    # 実装は省略（必要に応じて実装）
    pass

@app.route('/health', methods=['GET'])
def health_check():
    """
    ヘルスチェック用エンドポイント
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'card-generator'
    })

@app.route('/generate-cards', methods=['POST'])
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
                # ファイル名にインデックスを追加
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
        
        # レスポンス用のデータを準備
        response_data = {
            'session_id': session_id,
            'cards': [],
            'timestamp': datetime.now().isoformat()
        }
        
        for card_info in cards_info:
            card_data = {
                'id': len(response_data['cards']) + 1,
                'name': card_info['name'],
                'power': card_info['power'],
                'card_url': f'/get-card/{session_id}/{os.path.basename(card_info["card_path"])}',
                'features': card_info['features']
            }
            response_data['cards'].append(card_data)
        
        # セッション情報を保存
        session_info_path = os.path.join(cards_folder, 'session_info.json')
        with open(session_info_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, ensure_ascii=False, indent=2)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/get-card/<session_id>/<card_filename>', methods=['GET'])
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
            session_info = json.load(f)
        
        return jsonify(session_info)
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving session info: {str(e)}'}), 500

@app.route('/cleanup-session/<session_id>', methods=['DELETE'])
def cleanup_session(session_id: str):
    """
    セッションのクリーンアップ
    """
    try:
        session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        cards_folder = os.path.join(app.config['CARDS_FOLDER'], session_id)
        
        if os.path.exists(session_folder):
            shutil.rmtree(session_folder)
        
        if os.path.exists(cards_folder):
            shutil.rmtree(cards_folder)
        
        return jsonify({'message': 'Session cleaned up successfully'})
        
    except Exception as e:
        return jsonify({'error': f'Error cleaning up session: {str(e)}'}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large'}), 413

@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Bad request'}), 400

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # 開発環境での実行
    app.run(debug=True, host='0.0.0.0', port=5000)