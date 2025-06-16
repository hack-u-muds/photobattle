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

# app.py の prepare_card_for_game_logic 関数を修正

def prepare_card_for_game_logic(card_info: dict, session_id: str, card_index: int) -> dict:
    """ゲームロジック担当者向けのカードデータを準備"""
    game_card = card_info['game_data'].copy()
    
    # IDを整数として明確に設定
    card_id = card_index + 1
    game_card['id'] = card_id
    game_card['card_image_url'] = f'/api/cards/{session_id}/card_{card_id}.png'
    
    # effectiveness_multipliersを安全な形式に変換
    effectiveness_multipliers = game_card.get('effectiveness_multipliers', {})
    safe_effectiveness = {}
    for key, value in effectiveness_multipliers.items():
        # Enumの場合は値を取得、そうでなければそのまま
        safe_key = key.value if hasattr(key, 'value') else str(key)
        safe_effectiveness[safe_key] = value
    
    result_card = {
        'id': card_id,  # 明確に整数として設定
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
    
    print(f"Generated card: ID={result_card['id']} (type: {type(result_card['id'])}), Name={result_card['name']}")
    return result_card

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
    """ルーム再参加（ページ移動時）- 強化版"""
    room_id = data['room_id'].upper()
    current_socket_id = request.sid
    
    print(f"=== Rejoin Room Debug (Enhanced) ===")
    print(f"Current Socket ID: {current_socket_id}")
    print(f"Room: {room_id}")
    
    if room_id not in rooms:
        print(f"ERROR: Room {room_id} not found")
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    current_players = room.get('players', [])
    player_cards = room.get('player_cards', {})
    available_card_owners = list(player_cards.keys())
    
    print(f"Current players in room: {current_players}")
    print(f"Available card owners: {available_card_owners}")
    print(f"Current socket already in players: {current_socket_id in current_players}")
    print(f"Current socket has cards: {current_socket_id in player_cards}")
    
    # ルームに参加
    join_room(room_id)
    
    # Case 1: 既にルームにいて、カードも持っている（正常状態）
    if current_socket_id in current_players and current_socket_id in player_cards:
        print(f"Player {current_socket_id} is already properly set up")
        return
    
    # Case 2: ルームにはいるが、カードがない（カードIDのみ移行が必要）
    if current_socket_id in current_players and current_socket_id not in player_cards:
        print(f"Player {current_socket_id} in room but missing cards")
        # 利用可能なカードの中から適切なものを割り当て
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        if unassigned_cards:
            old_card_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_card_owner]
            del player_cards[old_card_owner]
            print(f"Migrated cards from {old_card_owner} to {current_socket_id}")
        return
    
    # Case 3: ルームにいないが、カードは持っている（プレイヤーIDのみ更新が必要）
    if current_socket_id not in current_players and current_socket_id in player_cards:
        print(f"Player {current_socket_id} has cards but not in player list")
        # プレイヤーリストを更新
        if len(current_players) < 2:
            current_players.append(current_socket_id)
        else:
            # 2人目の場合、適切なポジションに配置
            current_players[1] = current_socket_id
        print(f"Updated player list: {current_players}")
        return
    
    # Case 4: 完全に新しいSocket ID（両方とも移行が必要）
    if current_socket_id not in current_players and current_socket_id not in player_cards:
        print(f"Player {current_socket_id} is completely new, need full migration")
        
        # 利用可能なカードの中から未使用のものを見つける
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        
        if unassigned_cards:
            # カード情報を移行
            old_card_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_card_owner]
            del player_cards[old_card_owner]
            print(f"Migrated cards from {old_card_owner} to {current_socket_id}")
            
            # プレイヤーリストを更新
            if len(current_players) < 2:
                current_players.append(current_socket_id)
                print(f"Added {current_socket_id} to player list")
            else:
                # 古いSocket IDを新しいものに置き換え
                for i, player_id in enumerate(current_players):
                    if player_id not in player_cards:  # このプレイヤーはもうカードを持っていない
                        current_players[i] = current_socket_id
                        print(f"Replaced player {player_id} with {current_socket_id}")
                        break
        else:
            print(f"No unassigned cards available for {current_socket_id}")
    
    # スコア情報も同期
    scores = room.get('scores', {})
    if current_socket_id not in scores:
        scores[current_socket_id] = 0
        # 古いSocket IDのスコアがあれば移行
        for old_id in list(scores.keys()):
            if old_id not in current_players and old_id != current_socket_id:
                if current_socket_id not in scores:
                    scores[current_socket_id] = scores[old_id]
                del scores[old_id]
                break
    
    # 最終状態をログ出力
    print(f"=== Final State After Rejoin ===")
    print(f"Players: {room['players']}")
    print(f"Player cards: {list(room['player_cards'].keys())}")
    print(f"Scores: {list(room.get('scores', {}).keys())}")


@socketio.on('cards_ready')
def cards_ready(data):
    """カード生成完了通知"""
    room_id = data['room_id'].upper()
    cards = data['cards']
    
    print(f"=== Cards Ready Debug ===")
    print(f"Player: {request.sid}")
    print(f"Room: {room_id}")
    print(f"Received cards: {len(cards)} cards")
    
    if room_id not in rooms:
        print(f"ERROR: Room {room_id} not found")
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    user_id = request.sid
    
    # プレイヤーがルームに参加していない場合、追加
    if user_id not in room.get('players', []):
        if len(room.get('players', [])) < 2:
            room.setdefault('players', []).append(user_id)
            print(f"Added player {user_id} to room")
        else:
            print(f"Room full, cannot add player {user_id}")
    
    # ユーザーのカード情報を保存
    if 'player_cards' not in room:
        room['player_cards'] = {}
    
    room['player_cards'][user_id] = cards
    print(f"Cards saved for player {user_id}")
    
    # スコア初期化
    if 'scores' not in room:
        room['scores'] = {}
    if user_id not in room['scores']:
        room['scores'][user_id] = 0
    
    # 相手に通知
    socketio.emit('opponent_cards_ready', {}, room=room_id, include_self=False)
    
    # 両プレイヤーのカードが準備完了かチェック
    if len(room['player_cards']) == 2:
        room['status'] = 'battle_ready'
        socketio.emit('both_players_ready', {
            'message': 'Both players are ready for battle!'
        }, room=room_id)
        print(f"Both players ready in room {room_id}")

@socketio.on('disconnect')
def on_disconnect():
    """クライアント切断時の処理を軽減"""
    print(f'Client disconnected: {request.sid}')
    # ルームからの即座削除はしない（ページ遷移の可能性があるため）
    # 代わりに一定時間後に削除するか、再接続を待つ


# デバッグ用エンドポイントを追加
@app.route('/debug/room/<room_id>')
def debug_room(room_id):
    """ルーム状態のデバッグ表示"""
    room_id = room_id.upper()
    if room_id not in rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[room_id]
    return jsonify({
        'room_id': room_id,
        'players': room.get('players', []),
        'player_cards': {
            player_id: len(cards) for player_id, cards in room.get('player_cards', {}).items()
        },
        'status': room.get('status'),
        'scores': room.get('scores', {})
    })


@app.route('/debug/migrate-cards/<room_id>')
def migrate_cards(room_id):
    """手動でカード情報を現在のプレイヤーに移行"""
    room_id = room_id.upper()
    if room_id not in rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[room_id]
    current_players = room.get('players', [])
    player_cards = room.get('player_cards', {})
    available_cards = list(player_cards.keys())
    
    migrations = []
    
    # 現在のプレイヤーIDと利用可能なカードIDをマッピング
    for i, player_id in enumerate(current_players):
        if player_id not in player_cards and i < len(available_cards):
            old_id = available_cards[i]
            player_cards[player_id] = player_cards[old_id]
            del player_cards[old_id]
            migrations.append(f"{old_id} -> {player_id}")
    
    return jsonify({
        'migrations': migrations,
        'current_players': current_players,
        'player_cards': list(player_cards.keys())
    })

# さらに、handle_card_selection 関数にもデバッグを強化
@socketio.on('card_selected')
def handle_card_selection(data):
    """カード選択の処理 - 自動修復機能付き"""
    room_id = data['room_id'].upper()
    card_id = data['card_id']
    current_socket_id = request.sid
    
    print(f"=== Card Selection Debug ===")
    print(f"Player: {current_socket_id}")
    print(f"Room: {room_id}")
    print(f"Card ID: {card_id} (type: {type(card_id)})")
    
    if room_id not in rooms:
        print(f"ERROR: Room {room_id} not found")
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    # 自動修復を試行
    if current_socket_id not in room.get('player_cards', {}):
        print(f"Player {current_socket_id} missing cards, attempting auto-repair...")
        
        current_players = room.get('players', [])
        player_cards = room.get('player_cards', {})
        available_card_owners = list(player_cards.keys())
        
        # 未割り当てのカードを探す
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        
        if unassigned_cards:
            old_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_owner]
            del player_cards[old_owner]
            
            # プレイヤーリストも更新
            if current_socket_id not in current_players:
                if len(current_players) < 2:
                    current_players.append(current_socket_id)
                else:
                    # 古いIDを置き換え
                    for i, pid in enumerate(current_players):
                        if pid not in player_cards:
                            current_players[i] = current_socket_id
                            break
            
            print(f"Auto-repaired: migrated cards from {old_owner} to {current_socket_id}")
        else:
            print(f"Auto-repair failed: no unassigned cards available")
            emit('error', {'message': 'カード情報が見つかりません。ページを再読み込みしてください。'})
            return
    
    # 以下は既存の処理...
    current_round = room['current_round']
    round_key = f"round_{current_round}"
    
    if 'current_selections' not in room:
        room['current_selections'] = {}
    
    if round_key not in room['current_selections']:
        room['current_selections'][round_key] = {}
    
    if current_socket_id in room['current_selections'][round_key]:
        emit('error', {'message': 'You have already selected a card for this round'})
        return
    
    user_cards = room.get('player_cards', {}).get(current_socket_id, [])
    
    if not user_cards:
        print(f"ERROR: Still no cards found for user {current_socket_id} after auto-repair")
        emit('error', {'message': 'カード情報の復旧に失敗しました。ページを再読み込みしてください。'})
        return
    
    # カード検索
    selected_card = None
    for card in user_cards:
        card_id_in_data = card.get('id')
        if (card_id_in_data == card_id or 
            str(card_id_in_data) == str(card_id) or
            (isinstance(card_id, (int, float)) and card_id_in_data == int(card_id)) or
            (isinstance(card_id_in_data, (int, float)) and int(card_id_in_data) == card_id)):
            selected_card = card
            break
    
    if not selected_card:
        print(f"ERROR: Card not found - ID: {card_id}")
        print(f"Available card IDs: {[c.get('id') for c in user_cards]}")
        emit('error', {'message': 'Invalid card selection'})
        return
    
    if selected_card.get('used', False):
        print(f"ERROR: Card already used - ID: {card_id}")
        emit('error', {'message': 'Card already used'})
        return
    
    # 選択を記録
    room['current_selections'][round_key][current_socket_id] = {
        'card': selected_card,
        'player_id': current_socket_id,
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

# app.py の process_battle 関数を修正

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
    
    # ★★★ 重要: カードを使用済みにマーク（両方のプレイヤーで） ★★★
    selected_card_ids = {
        player1: selections[player1]['card']['id'],
        player2: selections[player2]['card']['id']
    }
    
    print(f"Marking cards as used: Player1 Card {selected_card_ids[player1]}, Player2 Card {selected_card_ids[player2]}")
    
    for player_id in [player1, player2]:
        player_cards = room['player_cards'][player_id]
        selected_card_id = selected_card_ids[player_id]
        
        # そのプレイヤーのカードリストで該当カードを使用済みにマーク
        for card in player_cards:
            if card['id'] == selected_card_id:
                card['used'] = True
                print(f"Marked card {selected_card_id} as used for player {player_id}")
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
        'battle_timestamp': datetime.now().isoformat(),
        # ★★★ 追加: 更新されたカード情報を送信 ★★★
        'updated_cards': {
            player1: room['player_cards'][player1],
            player2: room['player_cards'][player2]
        }
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
                'message': f'Round {room["current_round"]} 開始！',
                # ★★★ 追加: 更新されたカード情報も送信 ★★★
                'updated_cards': {
                    player1: room['player_cards'][player1],
                    player2: room['player_cards'][player2]
                }
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

# app.py に追加する緊急修復用エンドポイント

@app.route('/debug/fix-room/<room_id>')
def fix_room(room_id):
    """ルーム状態を自動修復"""
    room_id = room_id.upper()
    if room_id not in rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[room_id]
    current_players = room.get('players', [])
    player_cards = room.get('player_cards', {})
    available_card_owners = list(player_cards.keys())
    
    fixes = []
    
    print(f"=== Auto-Fixing Room {room_id} ===")
    print(f"Current players: {current_players}")
    print(f"Card owners: {available_card_owners}")
    
    # 修復1: プレイヤーリストとカード所有者の同期
    if len(available_card_owners) == 2 and len(current_players) == 2:
        # カード所有者をプレイヤーリストに反映
        new_players = available_card_owners.copy()
        if new_players != current_players:
            room['players'] = new_players
            fixes.append(f"Updated players from {current_players} to {new_players}")
    
    # 修復2: 孤立したカード情報の整理
    elif len(available_card_owners) > len(current_players):
        # カード情報の方が多い場合、プレイヤーリストを更新
        room['players'] = available_card_owners[:2]  # 最大2人
        fixes.append(f"Synced players to card owners: {room['players']}")
    
    # 修復3: スコア情報の同期
    scores = room.get('scores', {})
    for player_id in room['players']:
        if player_id not in scores:
            scores[player_id] = 0
            fixes.append(f"Added score for {player_id}")
    
    # 不要なスコアを削除
    for score_owner in list(scores.keys()):
        if score_owner not in room['players']:
            del scores[score_owner]
            fixes.append(f"Removed obsolete score for {score_owner}")
    
    return jsonify({
        'room_id': room_id,
        'fixes_applied': fixes,
        'final_state': {
            'players': room['players'],
            'card_owners': list(room['player_cards'].keys()),
            'scores': room.get('scores', {})
        }
    })


@app.route('/debug/force-sync/<room_id>/<player1_id>/<player2_id>')
def force_sync(room_id, player1_id, player2_id):
    """強制的にプレイヤーIDを同期"""
    room_id = room_id.upper()
    if room_id not in rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[room_id]
    player_cards = room.get('player_cards', {})
    available_cards = list(player_cards.keys())
    
    changes = []
    
    # プレイヤーリストを強制更新
    room['players'] = [player1_id, player2_id]
    changes.append(f"Force updated players to [{player1_id}, {player2_id}]")
    
    # カード情報を適切に割り当て
    if len(available_cards) >= 2:
        # 1人目のカード
        if player1_id not in player_cards and len(available_cards) > 0:
            old_owner = available_cards[0]
            player_cards[player1_id] = player_cards[old_owner]
            del player_cards[old_owner]
            changes.append(f"Migrated cards: {old_owner} -> {player1_id}")
            available_cards.remove(old_owner)
        
        # 2人目のカード
        if player2_id not in player_cards and len(available_cards) > 0:
            old_owner = available_cards[0]
            player_cards[player2_id] = player_cards[old_owner]
            del player_cards[old_owner]
            changes.append(f"Migrated cards: {old_owner} -> {player2_id}")
    
    # スコアを同期
    scores = room.setdefault('scores', {})
    scores[player1_id] = scores.get(player1_id, 0)
    scores[player2_id] = scores.get(player2_id, 0)
    
    # 不要なスコアを削除
    for old_score_owner in list(scores.keys()):
        if old_score_owner not in [player1_id, player2_id]:
            del scores[old_score_owner]
            changes.append(f"Removed old score for {old_score_owner}")
    
    return jsonify({
        'room_id': room_id,
        'changes': changes,
        'final_state': {
            'players': room['players'],
            'card_owners': list(room['player_cards'].keys()),
            'scores': room['scores']
        }
    })


@app.route('/debug/room-status/<room_id>')
def detailed_room_status(room_id):
    """詳細なルーム状態を表示"""
    room_id = room_id.upper()
    if room_id not in rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    room = rooms[room_id]
    
    # プレイヤーとカードの詳細分析
    current_players = room.get('players', [])
    player_cards = room.get('player_cards', {})
    scores = room.get('scores', {})
    
    analysis = {
        'room_id': room_id,
        'status': room.get('status', 'unknown'),
        'current_round': room.get('current_round', 1),
        'players': {
            'count': len(current_players),
            'list': current_players
        },
        'cards': {
            'owners_count': len(player_cards),
            'owners': list(player_cards.keys()),
            'details': {}
        },
        'scores': scores,
        'issues': []
    }
    
    # カードの詳細情報
    for owner, cards in player_cards.items():
        analysis['cards']['details'][owner] = {
            'card_count': len(cards),
            'card_ids': [c.get('id') for c in cards],
            'used_cards': [c.get('id') for c in cards if c.get('used', False)]
        }
    
    # 問題の検出
    if len(current_players) != len(player_cards):
        analysis['issues'].append(f"Player count mismatch: {len(current_players)} players vs {len(player_cards)} card owners")
    
    for player in current_players:
        if player not in player_cards:
            analysis['issues'].append(f"Player {player} has no cards")
    
    for card_owner in player_cards:
        if card_owner not in current_players:
            analysis['issues'].append(f"Card owner {card_owner} not in player list")
    
    return jsonify(analysis)


# フロントエンド用の自動修復関数
@app.route('/api/auto-repair/<room_id>')
def api_auto_repair(room_id):
    """APIとして呼び出し可能な自動修復"""
    try:
        # fix_room を実行
        result = fix_room(room_id)
        return result
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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