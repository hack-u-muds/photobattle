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
# app.py のSocket.IO部分を以下で置き換え

import math

# ===== Socket.IO イベントハンドラー =====
@socketio.on('connect')
def on_connect():
    print(f'Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to server'})

@socketio.on('disconnect')
def on_disconnect():
    print(f'Client disconnected: {request.sid}')
    # ルームからプレイヤーを削除
    for room_id, room in rooms.items():
        if request.sid in room.get('players', []):
            room['players'].remove(request.sid)
            socketio.emit('player_disconnected', {
                'player_id': request.sid,
                'players_count': len(room['players'])
            }, room=room_id)
            break

@socketio.on('create_room')
def create_room():
    """ルーム作成"""
    room_id = str(uuid.uuid4())[:8].upper()
    rooms[room_id] = {
        'players': [request.sid],
        'status': 'waiting',
        'current_round': 1,
        'max_rounds': 3,
        'scores': {request.sid: 0},
        'player_cards': {},
        'current_selections': {},
        'battle_history': [],
        'created_at': datetime.now().isoformat()
    }
    join_room(room_id)
    
    emit('room_created', {
        'room_id': room_id,
        'message': f'Room {room_id} created successfully'
    })
    print(f"Room created: {room_id} by {request.sid}")

@socketio.on('join_room_request')
def join_room_request(data):
    """ルーム参加"""
    room_id = data['room_id'].upper()
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    if len(room['players']) >= 2:
        emit('error', {'message': 'Room is full'})
        return
        
    if request.sid in room['players']:
        emit('error', {'message': 'Already in this room'})
        return
    
    join_room(room_id)
    room['players'].append(request.sid)
    room['scores'][request.sid] = 0
    
    emit('room_joined', {
        'room_id': room_id,
        'players_count': len(room['players'])
    })
    
    # 部屋の全員に通知
    socketio.emit('player_joined', {
        'players_count': len(room['players'])
    }, room=room_id)
    
    # 2人揃ったらゲーム開始可能状態に
    if len(room['players']) == 2:
        room['status'] = 'ready'
        socketio.emit('game_ready', {
            'message': 'Both players joined. Ready to start!'
        }, room=room_id)
    
    print(f"Player {request.sid} joined room {room_id}")

@socketio.on('rejoin_room')
def rejoin_room(data):
    """ルーム再参加（ページ移動時）"""
    room_id = data['room_id'].upper()
    if room_id in rooms:
        join_room(room_id)
        print(f"Player {request.sid} rejoined room {room_id}")

@socketio.on('cards_ready')
def cards_ready(data):
    """カード生成完了通知"""
    room_id = data['room_id'].upper()
    cards = data['cards']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    # ユーザーのカード情報を保存
    if 'player_cards' not in room:
        room['player_cards'] = {}
    
    room['player_cards'][request.sid] = cards
    
    print(f"Cards ready for player {request.sid} in room {room_id}")
    
    # 相手に通知
    socketio.emit('opponent_cards_ready', {}, room=room_id, include_self=False)
    
    # 両プレイヤーのカードが準備完了かチェック
    if len(room['player_cards']) == 2:
        room['status'] = 'battle_ready'
        socketio.emit('both_players_ready', {
            'message': 'Both players are ready for battle!'
        }, room=room_id)
        print(f"Both players ready in room {room_id}")

@socketio.on('card_selected')
def handle_card_selection(data):
    """カード選択の処理"""
    room_id = data['room_id'].upper()
    card_id = data['card_id']
    
    print(f"=== Card Selection Debug ===")
    print(f"Player: {request.sid}")
    print(f"Room: {room_id}")
    print(f"Card ID: {card_id}")
    
    if room_id not in rooms:
        print(f"ERROR: Room {room_id} not found")
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    user_id = request.sid
    
    # 現在のラウンドの選択状況をチェック
    current_round = room['current_round']
    round_key = f"round_{current_round}"
    
    if 'current_selections' not in room:
        room['current_selections'] = {}
    
    if round_key not in room['current_selections']:
        room['current_selections'][round_key] = {}
    
    # プレイヤーがすでにこのラウンドで選択済みかチェック
    if user_id in room['current_selections'][round_key]:
        emit('error', {'message': 'You have already selected a card for this round'})
        return
    
    # ユーザーのカードから選択されたカードを取得
    user_cards = room.get('player_cards', {}).get(user_id, [])
    selected_card = next((c for c in user_cards if c['id'] == card_id), None)
    
    if not selected_card:
        print(f"ERROR: Card not found - ID: {card_id}")
        emit('error', {'message': 'Invalid card selection'})
        return
    
    # カードが既に使用済みかチェック
    if selected_card.get('used', False):
        print(f"ERROR: Card already used - ID: {card_id}")
        emit('error', {'message': 'Card already used'})
        return
    
    # 選択を記録
    room['current_selections'][round_key][user_id] = {
        'card': selected_card,
        'player_id': user_id,
        'selected_at': datetime.now().isoformat()
    }
    
    print(f"Card selected: {selected_card['name']} (Power: {selected_card['attack_power']}, Attribute: {selected_card['attribute']})")
    print(f"Selections this round: {len(room['current_selections'][round_key])}/2")
    
    # 相手に選択完了を通知
    socketio.emit('opponent_card_selected', {
        'message': 'Opponent has selected a card'
    }, room=room_id, include_self=False)
    
    # 両プレイヤーが選択完了したら戦闘処理
    if len(room['current_selections'][round_key]) == 2:
        print("Both players selected - processing battle")
        process_battle(room_id, current_round)
    else:
        print("Waiting for other player...")

def calculate_battle_power(attacker_card, defender_card):
    """属性相性を考慮した攻撃力計算"""
    base_power = attacker_card['attack_power']
    attacker_attr = attacker_card['attribute']
    defender_attr = defender_card['attribute']
    
    # 属性相性マップ (攻撃側 -> 防御側 -> 有利かどうか)
    effectiveness = {
        '火': {'土': True, '水': False, '火': False},  # 火は土に有利
        '水': {'火': True, '土': False, '水': False},  # 水は火に有利  
        '土': {'水': True, '火': False, '土': False}   # 土は水に有利
    }
    
    # 相性チェック
    is_effective = effectiveness.get(attacker_attr, {}).get(defender_attr, False)
    
    if is_effective:
        # 1.5倍（切り上げ）
        effective_power = math.ceil(base_power * 1.5)
        multiplier = 1.5
        effectiveness_text = "有利"
    else:
        effective_power = base_power
        multiplier = 1.0
        effectiveness_text = "等倍" if attacker_attr == defender_attr else "不利"
    
    return {
        'base_power': base_power,
        'effective_power': effective_power,
        'multiplier': multiplier,
        'effectiveness': effectiveness_text,
        'is_effective': is_effective
    }

def process_battle(room_id, round_number):
    """戦闘処理"""
    room = rooms[room_id]
    round_key = f"round_{round_number}"
    selections = room['current_selections'][round_key]
    
    players = list(selections.keys())
    if len(players) != 2:
        print(f"ERROR: Invalid player count: {len(players)}")
        return
    
    player1, player2 = players[0], players[1]
    
    card1 = selections[player1]['card']
    card2 = selections[player2]['card']
    
    print(f"\n=== Battle Round {round_number} ===")
    print(f"Player 1 ({player1}): {card1['name']} (Power: {card1['attack_power']}, Attr: {card1['attribute']})")
    print(f"Player 2 ({player2}): {card2['name']} (Power: {card2['attack_power']}, Attr: {card2['attribute']})")
    
    # 各プレイヤーの攻撃力計算
    player1_battle = calculate_battle_power(card1, card2)
    player2_battle = calculate_battle_power(card2, card1)
    
    print(f"Player 1 effective power: {player1_battle['effective_power']} ({player1_battle['effectiveness']})")
    print(f"Player 2 effective power: {player2_battle['effective_power']} ({player2_battle['effectiveness']})")
    
    # 勝敗判定
    if player1_battle['effective_power'] > player2_battle['effective_power']:
        winner = player1
        loser = player2
        winner_card = card1
        loser_card = card2
        winner_battle = player1_battle
        loser_battle = player2_battle
    elif player2_battle['effective_power'] > player1_battle['effective_power']:
        winner = player2
        loser = player1
        winner_card = card2
        loser_card = card1
        winner_battle = player2_battle
        loser_battle = player1_battle
    else:
        winner = None  # 引き分け
        winner_card = None
        loser_card = None
        winner_battle = None
        loser_battle = None
    
    # スコア更新
    if winner:
        room['scores'][winner] = room['scores'].get(winner, 0) + 1
        print(f"Winner: {winner}")
    else:
        print("Draw!")
    
    print(f"Current scores: {room['scores']}")
    
    # カードを使用済みにマーク
    for player_id in [player1, player2]:
        player_cards = room['player_cards'][player_id]
        for card in player_cards:
            if card['id'] == selections[player_id]['card']['id']:
                card['used'] = True
                break
    
    # バトル結果データを作成
    battle_result = {
        'round': round_number,
        'players': {
            player1: {
                'card': card1,
                'battle_power': player1_battle,
                'player_id': player1
            },
            player2: {
                'card': card2,
                'battle_power': player2_battle,
                'player_id': player2
            }
        },
        'winner': winner,
        'winner_card': winner_card,
        'loser_card': loser_card,
        'scores': room['scores'].copy(),
        'is_draw': winner is None,
        'battle_timestamp': datetime.now().isoformat()
    }
    
    # バトル履歴に保存
    if 'battle_history' not in room:
        room['battle_history'] = []
    room['battle_history'].append(battle_result)
    
    # 戦闘結果を全員に送信
    socketio.emit('battle_result', battle_result, room=room_id)
    
    # ゲーム終了判定
    max_score = max(room['scores'].values()) if room['scores'] else 0
    total_rounds_played = round_number
    
    # 2勝先取 または 3ラウンド終了でゲーム終了
    if max_score >= 2 or total_rounds_played >= 3:
        # 最終勝者を決定
        player_scores = [(pid, score) for pid, score in room['scores'].items()]
        player_scores.sort(key=lambda x: x[1], reverse=True)
        
        if len(player_scores) >= 2 and player_scores[0][1] > player_scores[1][1]:
            final_winner = player_scores[0][0]
        else:
            final_winner = None  # 同点の場合
        
        game_end_data = {
            'winner': final_winner,
            'final_scores': room['scores'].copy(),
            'total_rounds': total_rounds_played,
            'battle_history': room['battle_history'],
            'game_end_reason': '2勝先取' if max_score >= 2 else '3ラウンド終了'
        }
        
        socketio.emit('game_finished', game_end_data, room=room_id)
        room['status'] = 'finished'
        
        print(f"Game finished in room {room_id}!")
        print(f"Final winner: {final_winner}")
        print(f"Final scores: {room['scores']}")
        
    else:
        # 次のラウンドへ
        room['current_round'] += 1
        
        # 短い遅延の後に次ラウンド開始
        def start_next_round():
            socketio.emit('next_round', {
                'round': room['current_round'],
                'message': f'Round {room["current_round"]} 開始！'
            }, room=room_id)
            print(f"Next round {room['current_round']} started in room {room_id}")
        
        # 3秒後に次ラウンド開始
        socketio.start_background_task(lambda: (
            socketio.sleep(3),
            start_next_round()
        ))

@socketio.on('request_rematch')
def handle_rematch(data):
    """再戦リクエスト"""
    room_id = data['room_id'].upper()
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    # ルームをリセット
    room.update({
        'status': 'battle_ready',
        'current_round': 1,
        'scores': {pid: 0 for pid in room['players']},
        'current_selections': {},
        'battle_history': []
    })
    
    # 全てのカードの使用状況をリセット
    for player_id, cards in room['player_cards'].items():
        for card in cards:
            card['used'] = False
    
    socketio.emit('rematch_started', {
        'message': 'Rematch started! Round 1 begins.'
    }, room=room_id)
    
    print(f"Rematch started in room {room_id}")

@socketio.on('test_message')
def handle_test_message(data):
    print(f'Received test message: {data}')
    emit('test_response', {'message': f'Server received: {data["message"]}'})

# デバッグ用：ルーム状態確認
@socketio.on('get_room_status')
def get_room_status(data):
    """ルーム状態確認（デバッグ用）"""
    room_id = data.get('room_id', '').upper()
    
    if room_id in rooms:
        room = rooms[room_id]
        emit('room_status', {
            'room_id': room_id,
            'status': room.get('status'),
            'current_round': room.get('current_round'),
            'players': room.get('players', []),
            'scores': room.get('scores', {}),
            'cards_ready': list(room.get('player_cards', {}).keys())
        })
    else:
        emit('error', {'message': 'Room not found'})

print("🎮 Photo Battle Socket.IO handlers loaded successfully!")

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