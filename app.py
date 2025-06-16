from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import uuid
from card_generator import CardGenerator
import base64
from io import BytesIO
import os
import json
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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

# 一時的なデータストレージ（後でDBに置き換え）
rooms = {}
users = {}

# カード生成用のインスタンス
card_generator = CardGenerator()

# ===== HTMLページのルーティング =====
@app.route('/')
def index():
    """トップページ（マッチング画面）"""
    return send_from_directory('.', 'matching.html')

@app.route('/matching')
@app.route('/matching.html')
def matching():
    """マッチング画面"""
    return send_from_directory('.', 'matching.html')

@app.route('/card-generation')
@app.route('/card-generation.html')
def card_generation():
    """カード生成画面"""
    return send_from_directory('.', 'card-generation.html')

@app.route('/battle')
@app.route('/battle.html')
def battle():
    """バトル画面"""
    return send_from_directory('.', 'battle.html')

# ===== API エンドポイント =====
def allowed_file(filename: str) -> bool:
    """アップロードされたファイルが許可された拡張子かチェック"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def prepare_card_for_game_logic(card_info: dict, session_id: str, card_index: int) -> dict:
    """ゲームロジック担当者向けのカードデータを準備"""
    game_card = card_info['game_data'].copy()
    game_card['id'] = card_index + 1
    game_card['card_image_url'] = f'/api/cards/{session_id}/card_{card_index + 1}.png'
    
    # effectiveness_multipliersを安全な形式に変換
    effectiveness_multipliers = game_card.get('effectiveness_multipliers', {})
    safe_effectiveness = {}
    for key, value in effectiveness_multipliers.items():
        # Enumの場合は値を取得、そうでなければそのまま
        safe_key = key.value if hasattr(key, 'value') else str(key)
        safe_effectiveness[safe_key] = value
    
    return {
        'id': game_card['id'],
        'name': card_info['name'],
        'attack_power': game_card['attack_power'],
        'attribute': game_card['attribute'],
        'attribute_en': game_card['attribute_en'],
        'card_image_url': game_card['card_image_url'],
        'used': game_card['used'],
        'effectiveness_info': {
            'strong_against': [attr for attr, mult in safe_effectiveness.items() if mult > 1.0],
            'weak_against': [attr for attr, mult in safe_effectiveness.items() if mult < 1.0],
            'normal_against': [attr for attr, mult in safe_effectiveness.items() if mult == 1.0]
        }
    }

@app.route('/api/health', methods=['GET'])
def health_check():
    """ヘルスチェック用エンドポイント"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'photo-battle-app',
        'version': '2.0.0',
        'features': ['socket_io', 'card_generation', 'battle_system']
    })

@app.route('/api/cards/generate', methods=['POST'])
def generate_cards():
    """3枚の画像からカードを生成するメインエンドポイント"""
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
        
        # ゲームロジック用のデータを準備
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
            'detailed_cards_info': cards_info
        }
        
        session_info_path = os.path.join(cards_folder, 'session_info.json')
        with open(session_info_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/cards/<session_id>/<card_filename>', methods=['GET'])
def get_card(session_id: str, card_filename: str):
    """生成されたカード画像を取得"""
    try:
        card_filename = secure_filename(card_filename)
        card_path = os.path.join(app.config['CARDS_FOLDER'], session_id, card_filename)
        
        if not os.path.exists(card_path):
            return jsonify({'error': 'Card not found'}), 404
        
        return send_from_directory(os.path.dirname(card_path), card_filename, mimetype='image/png')
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving card: {str(e)}'}), 500

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session_info(session_id: str):
    """セッション情報を取得"""
    try:
        session_info_path = os.path.join(app.config['CARDS_FOLDER'], session_id, 'session_info.json')
        
        if not os.path.exists(session_info_path):
            return jsonify({'error': 'Session not found'}), 404
        
        with open(session_info_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        return jsonify(session_data['response_data'])
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving session info: {str(e)}'}), 500

# ===== Socket.IO イベントハンドラー =====
@socketio.on('connect')
def on_connect():
    print(f'Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to server'})

@socketio.on('disconnect')
def on_disconnect():
    print(f'Client disconnected: {request.sid}')

@socketio.on('create_room')
def create_room():
    """ルーム作成"""
    room_id = str(uuid.uuid4())[:8].upper()
    rooms[room_id] = {
        'players': [],
        'status': 'waiting',
        'current_round': 0,
        'scores': {}
    }
    join_room(room_id)
    rooms[room_id]['players'].append(request.sid)
    rooms[room_id]['scores'][request.sid] = 0
    
    emit('room_created', {
        'room_id': room_id,
        'message': f'Room {room_id} created successfully'
    })

@socketio.on('join_room_request')
def join_room_request(data):
    """ルーム参加"""
    room_id = data['room_id'].upper()
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    if len(rooms[room_id]['players']) >= 2:
        emit('error', {'message': 'Room is full'})
        return
    
    join_room(room_id)
    rooms[room_id]['players'].append(request.sid)
    rooms[room_id]['scores'][request.sid] = 0
    
    emit('room_joined', {
        'room_id': room_id,
        'players_count': len(rooms[room_id]['players'])
    })
    
    # 部屋の全員に通知
    socketio.emit('player_joined', {
        'players_count': len(rooms[room_id]['players'])
    }, room=room_id)
    
    # 2人揃ったらゲーム開始可能状態に
    if len(rooms[room_id]['players']) == 2:
        rooms[room_id]['status'] = 'ready'
        socketio.emit('game_ready', {
            'message': 'Both players joined. Ready to start!'
        }, room=room_id)

@socketio.on('rejoin_room')
def rejoin_room(data):
    """ルーム再参加（ページ移動時）"""
    room_id = data['room_id'].upper()
    if room_id in rooms:
        join_room(room_id)

@socketio.on('cards_ready')
def cards_ready(data):
    """カード生成完了通知"""
    room_id = data['room_id']
    cards = data['cards']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    # ユーザーのカード情報を保存
    if 'player_cards' not in rooms[room_id]:
        rooms[room_id]['player_cards'] = {}
    
    rooms[room_id]['player_cards'][request.sid] = cards
    
    # 相手に通知
    socketio.emit('opponent_cards_ready', {}, room=room_id, include_self=False)
    
    # 両プレイヤーのカードが準備完了かチェック
    if len(rooms[room_id]['player_cards']) == 2:
        socketio.emit('both_players_ready', {
            'message': 'Both players are ready for battle!'
        }, room=room_id)

@socketio.on('card_selected')
def handle_card_selection(data):
    """カード選択の処理"""
    room_id = data['room_id']
    card_id = data['card_id']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    user_id = request.sid
    
    # カード選択を記録
    if 'current_selections' not in room:
        room['current_selections'] = {}
    
    # ユーザーのカードから選択されたカードを取得
    user_cards = room.get('player_cards', {}).get(user_id, [])
    selected_card = next((c for c in user_cards if c['id'] == card_id and not c['used']), None)
    
    if not selected_card:
        emit('error', {'message': 'Invalid card selection'})
        return
    
    room['current_selections'][user_id] = {
        'card': selected_card,
        'player_id': user_id
    }
    
    # 両プレイヤーが選択完了したら戦闘処理
    if len(room['current_selections']) == 2:
        process_battle(room_id)

def calculate_battle_power(base_power, my_attr, opponent_attr):
    """属性相性を考慮した攻撃力計算"""
    multipliers = {
        ('fire', 'earth'): 1.2,
        ('earth', 'water'): 1.2,
        ('water', 'fire'): 1.2,
        # 逆相性
        ('earth', 'fire'): 0.8,
        ('water', 'earth'): 0.8,
        ('fire', 'water'): 0.8
    }
    
    # 日本語から英語への変換
    attr_map = {'火': 'fire', '水': 'water', '土': 'earth'}
    my_attr_en = attr_map.get(my_attr, my_attr)
    opponent_attr_en = attr_map.get(opponent_attr, opponent_attr)
    
    multiplier = multipliers.get((my_attr_en, opponent_attr_en), 1.0)
    return int(base_power * multiplier)

def process_battle(room_id):
    """戦闘処理"""
    room = rooms[room_id]
    selections = room['current_selections']
    
    players = list(selections.keys())
    player1, player2 = players[0], players[1]
    
    card1 = selections[player1]['card']
    card2 = selections[player2]['card']
    
    # 属性相性を考慮した攻撃力計算
    power1 = calculate_battle_power(card1['attack_power'], card1['attribute'], card2['attribute'])
    power2 = calculate_battle_power(card2['attack_power'], card2['attribute'], card1['attribute'])
    
    # 勝敗判定
    if power1 > power2:
        winner = player1
    elif power2 > power1:
        winner = player2
    else:
        winner = None  # 引き分け
    
    # スコア更新
    if winner:
        room['scores'][winner] = room['scores'].get(winner, 0) + 1
    
    # カードを使用済みに
    for card in room['player_cards'][player1]:
        if card['id'] == card1['id']:
            card['used'] = True
    for card in room['player_cards'][player2]:
        if card['id'] == card2['id']:
            card['used'] = True
    
    # 戦闘結果を送信
    battle_result = {
        'round': room['current_round'] + 1,
        'player1': {
            'card': card1,
            'power': power1,
            'player_id': player1
        },
        'player2': {
            'card': card2,
            'power': power2,
            'player_id': player2
        },
        'winner': winner,
        'scores': room['scores']
    }
    
    socketio.emit('battle_result', battle_result, room=room_id)
    
    # ラウンド進行
    room['current_round'] += 1
    room['current_selections'] = {}
    
    # ゲーム終了判定（2勝先取）
    max_score = max(room['scores'].values()) if room['scores'] else 0
    if max_score >= 2:
        final_winner = [pid for pid, score in room['scores'].items() if score >= 2][0]
        socketio.emit('game_finished', {
            'winner': final_winner,
            'final_scores': room['scores']
        }, room=room_id)
        room['status'] = 'finished'
    else:
        # 次のラウンドへ
        socketio.emit('next_round', {
            'round': room['current_round'] + 1
        }, room=room_id)

@socketio.on('test_message')
def handle_test_message(data):
    print(f'Received test message: {data}')
    emit('test_response', {'message': f'Server received: {data["message"]}'})

# エラーハンドラー
@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large (max 16MB)'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    print("🎮 Photo Battle Full Stack Server v2.0.0")
    print("📋 Features:")
    print("   - HTML Pages: matching, card-generation, battle")
    print("   - Socket.IO: Real-time multiplayer")
    print("   - API: Card generation and image processing")
    print("   - Game Logic: Battle system with attribute effectiveness")
    print("🚀 Server starting...")
    print("🌐 Access URLs:")
    print("   - Main: http://localhost:5000/")
    print("   - Matching: http://localhost:5000/matching.html")
    print("   - Card Gen: http://localhost:5000/card-generation.html")
    print("   - Battle: http://localhost:5000/battle.html")
    
    # 開発環境での実行
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)