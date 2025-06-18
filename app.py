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
import socket
import math

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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# フォルダの作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CARDS_FOLDER, exist_ok=True)

# データストレージ
rooms = {}
users = {}

# カード生成用のインスタンス
card_generator = CardGenerator()

# HTMLページのルーティング
@app.route('/')
def index():
    return send_from_directory('.', 'matching.html')

@app.route('/matching')
@app.route('/matching.html')
def matching():
    return send_from_directory('.', 'matching.html')

@app.route('/card-generation')
@app.route('/card-generation.html')
def card_generation():
    return send_from_directory('.', 'card-generation.html')

@app.route('/battle')
@app.route('/battle.html')
def battle():
    return send_from_directory('.', 'battle.html')

# API エンドポイント
def allowed_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def prepare_card_for_game_logic(card_info: dict, session_id: str, card_index: int) -> dict:
    game_card = card_info['game_data'].copy()
    
    card_id = card_index + 1
    game_card['id'] = card_id
    game_card['card_image_url'] = f'/api/cards/{session_id}/card_{card_id}.png'
    
    effectiveness_multipliers = game_card.get('effectiveness_multipliers', {})
    safe_effectiveness = {}
    for key, value in effectiveness_multipliers.items():
        safe_key = key.value if hasattr(key, 'value') else str(key)
        safe_effectiveness[safe_key] = value
    
    result_card = {
        'id': card_id,
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
    
    return result_card

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'photo-battle-app',
        'version': '2.0.0',
        'features': ['socket_io', 'card_generation', 'battle_system']
    })

@app.route('/api/cards/generate', methods=['POST'])
def generate_cards():
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'No images provided'}), 400
        
        files = request.files.getlist('images')
        
        if len(files) != 3:
            return jsonify({'error': 'Exactly 3 images required'}), 400
        
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
        cards_folder = os.path.join(app.config['CARDS_FOLDER'], session_id)
        
        os.makedirs(session_folder, exist_ok=True)
        os.makedirs(cards_folder, exist_ok=True)
        
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
                shutil.rmtree(session_folder, ignore_errors=True)
                shutil.rmtree(cards_folder, ignore_errors=True)
                return jsonify({'error': f'Invalid file: {file.filename}'}), 400
        
        cards_info = card_generator.generate_cards_batch(uploaded_files, cards_folder)
        
        if len(cards_info) == 0:
            return jsonify({'error': 'Failed to generate any cards'}), 500
        
        game_cards = []
        for i, card_info in enumerate(cards_info):
            game_card = prepare_card_for_game_logic(card_info, session_id, i)
            game_cards.append(game_card)
        
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
    try:
        session_info_path = os.path.join(app.config['CARDS_FOLDER'], session_id, 'session_info.json')
        
        if not os.path.exists(session_info_path):
            return jsonify({'error': 'Session not found'}), 404
        
        with open(session_info_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        return jsonify(session_data['response_data'])
        
    except Exception as e:
        return jsonify({'error': f'Error retrieving session info: {str(e)}'}), 500

# Socket.IO イベントハンドラー
@socketio.on('connect')
def on_connect():
    emit('connected', {'message': 'Connected to server'})

@socketio.on('disconnect')
def on_disconnect():
    pass

@socketio.on('create_room')
def create_room():
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

@socketio.on('join_room_request')
def join_room_request(data):
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
    
    socketio.emit('player_joined', {
        'players_count': len(room['players'])
    }, room=room_id)
    
    if len(room['players']) == 2:
        room['status'] = 'ready'
        socketio.emit('game_ready', {
            'message': 'Both players joined. Ready to start!'
        }, room=room_id)

@socketio.on('rejoin_room')
def rejoin_room(data):
    room_id = data['room_id'].upper()
    current_socket_id = request.sid
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    current_players = room.get('players', [])
    player_cards = room.get('player_cards', {})
    available_card_owners = list(player_cards.keys())
    
    join_room(room_id)
    
    # スコアの初期化を確実に行う
    if 'scores' not in room:
        room['scores'] = {}
    
    if current_socket_id in current_players and current_socket_id in player_cards:
        # 既に参加済みで、カードも持っている場合
        if current_socket_id not in room['scores']:
            room['scores'][current_socket_id] = 0
        return
    
    if current_socket_id in current_players and current_socket_id not in player_cards:
        # プレイヤーリストにはいるが、カードがない場合
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        if unassigned_cards:
            old_card_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_card_owner]
            del player_cards[old_card_owner]
        if current_socket_id not in room['scores']:
            room['scores'][current_socket_id] = 0
        return
    
    if current_socket_id not in current_players and current_socket_id in player_cards:
        # プレイヤーリストにはいないが、カードはある場合
        if len(current_players) < 2:
            current_players.append(current_socket_id)
        else:
            current_players[1] = current_socket_id
        if current_socket_id not in room['scores']:
            room['scores'][current_socket_id] = 0
        return
    
    if current_socket_id not in current_players and current_socket_id not in player_cards:
        # 新規参加の場合
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        
        if unassigned_cards:
            old_card_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_card_owner]
            del player_cards[old_card_owner]
            
            if len(current_players) < 2:
                current_players.append(current_socket_id)
            else:
                for i, player_id in enumerate(current_players):
                    if player_id not in player_cards:
                        current_players[i] = current_socket_id
                        break
        
        # スコアを確実に設定
        if current_socket_id not in room['scores']:
            room['scores'][current_socket_id] = 0
    
    # 古いスコアデータのクリーンアップ
    valid_players = set(current_players)
    for old_id in list(room['scores'].keys()):
        if old_id not in valid_players and old_id not in player_cards:
            del room['scores'][old_id]

@socketio.on('cards_ready')
def cards_ready(data):
    room_id = data['room_id'].upper()
    cards = data['cards']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    user_id = request.sid
    
    if user_id not in room.get('players', []):
        if len(room.get('players', [])) < 2:
            room.setdefault('players', []).append(user_id)
    
    if 'player_cards' not in room:
        room['player_cards'] = {}
    
    room['player_cards'][user_id] = cards
    
    if 'scores' not in room:
        room['scores'] = {}
    if user_id not in room['scores']:
        room['scores'][user_id] = 0
    
    socketio.emit('opponent_cards_ready', {}, room=room_id, include_self=False)
    
    if len(room['player_cards']) == 2:
        room['status'] = 'battle_ready'
        socketio.emit('both_players_ready', {
            'message': 'Both players are ready for battle!'
        }, room=room_id)

@socketio.on('card_selected')
def handle_card_selection(data):
    room_id = data['room_id'].upper()
    card_id = data['card_id']
    current_socket_id = request.sid
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    if current_socket_id not in room.get('player_cards', {}):
        current_players = room.get('players', [])
        player_cards = room.get('player_cards', {})
        available_card_owners = list(player_cards.keys())
        
        unassigned_cards = [owner for owner in available_card_owners if owner not in current_players]
        
        if unassigned_cards:
            old_owner = unassigned_cards[0]
            player_cards[current_socket_id] = player_cards[old_owner]
            del player_cards[old_owner]
            
            if current_socket_id not in current_players:
                if len(current_players) < 2:
                    current_players.append(current_socket_id)
                else:
                    for i, pid in enumerate(current_players):
                        if pid not in player_cards:
                            current_players[i] = current_socket_id
                            break
        else:
            emit('error', {'message': 'カード情報が見つかりません。ページを再読み込みしてください。'})
            return
    
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
        emit('error', {'message': 'カード情報の復旧に失敗しました。ページを再読み込みしてください。'})
        return
    
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
        emit('error', {'message': 'Invalid card selection'})
        return
    
    if selected_card.get('used', False):
        emit('error', {'message': 'Card already used'})
        return
    
    room['current_selections'][round_key][current_socket_id] = {
        'card': selected_card,
        'player_id': current_socket_id,
        'selected_at': datetime.now().isoformat()
    }
    
    socketio.emit('opponent_card_selected', {
        'message': 'Opponent has selected a card'
    }, room=room_id, include_self=False)
    
    if len(room['current_selections'][round_key]) == 2:
        process_battle(room_id, current_round)

def calculate_battle_power(attacker_card, defender_card):
    base_power = attacker_card['attack_power']
    attacker_attr = attacker_card['attribute']
    defender_attr = defender_card['attribute']
    
    effectiveness = {
        '火': {'土': True, '水': False, '火': False},
        '水': {'火': True, '土': False, '水': False},
        '土': {'水': True, '火': False, '土': False}
    }
    
    is_effective = effectiveness.get(attacker_attr, {}).get(defender_attr, False)
    
    if is_effective:
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
    room = rooms[room_id]
    round_key = f"round_{round_number}"
    selections = room['current_selections'][round_key]
    
    players = list(selections.keys())
    if len(players) != 2:
        print(f"ERROR: Expected 2 players, got {len(players)}")
        return
    
    player1, player2 = players[0], players[1]
    
    card1 = selections[player1]['card']
    card2 = selections[player2]['card']
    
    player1_battle = calculate_battle_power(card1, card2)
    player2_battle = calculate_battle_power(card2, card1)
    
    # 勝者判定
    winner = None
    winner_card = None
    loser_card = None
    winner_battle = None
    loser_battle = None
    
    if player1_battle['effective_power'] > player2_battle['effective_power']:
        winner = player1
        winner_card = card1
        loser_card = card2
        winner_battle = player1_battle
        loser_battle = player2_battle
    elif player2_battle['effective_power'] > player1_battle['effective_power']:
        winner = player2
        winner_card = card2
        loser_card = card1
        winner_battle = player2_battle
        loser_battle = player1_battle
    # else: 引き分けの場合はwinnerはNoneのまま
    
    # スコア更新（修正版）
    if 'scores' not in room:
        room['scores'] = {}
    
    # 両プレイヤーのスコアを確実に初期化
    if player1 not in room['scores']:
        room['scores'][player1] = 0
    if player2 not in room['scores']:
        room['scores'][player2] = 0
    
    print(f"DEBUG: Before score update - Player1: {room['scores'][player1]}, Player2: {room['scores'][player2]}")
    
    # 勝者のスコアを増加
    if winner:
        room['scores'][winner] += 1
        print(f"DEBUG: Winner {winner} score updated to {room['scores'][winner]}")
    
    print(f"DEBUG: After score update - All scores: {room['scores']}")
    
    # カードを使用済みにマーク
    player1_card_id = card1['id']
    player1_cards = room['player_cards'][player1]
    for card in player1_cards:
        if (str(card['id']) == str(player1_card_id) or 
            card['id'] == player1_card_id):
            card['used'] = True
            break
    
    player2_card_id = card2['id']
    player2_cards = room['player_cards'][player2]
    for card in player2_cards:
        if (str(card['id']) == str(player2_card_id) or 
            card['id'] == player2_card_id):
            card['used'] = True
            break
    
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
        'scores': room['scores'].copy(),  # 最新のスコアを送信
        'is_draw': winner is None,
        'battle_timestamp': datetime.now().isoformat(),
        'room_id': room_id,
        'used_cards': {
            player1: player1_card_id,
            player2: player2_card_id
        }
    }
    
    if 'battle_history' not in room:
        room['battle_history'] = []
    room['battle_history'].append(battle_result)
    
    print(f"DEBUG: Sending battle result with scores: {battle_result['scores']}")
    socketio.emit('battle_result', battle_result, room=room_id)
    
    for player_id, cards in room['player_cards'].items():
        socketio.emit('sync_card_status', {
            'cards': cards,
            'message': 'Card status synchronized',
            'round': round_number
        }, room=player_id)
    
    max_score = max(room['scores'].values()) if room['scores'] else 0
    total_rounds_played = round_number
    
    if max_score >= 2 or total_rounds_played >= 3:
        player_scores = [(pid, score) for pid, score in room['scores'].items()]
        player_scores.sort(key=lambda x: x[1], reverse=True)
        
        if len(player_scores) >= 2 and player_scores[0][1] > player_scores[1][1]:
            final_winner = player_scores[0][0]
        else:
            final_winner = None
        
        game_end_data = {
            'winner': final_winner,
            'final_scores': room['scores'].copy(),
            'total_rounds': total_rounds_played,
            'battle_history': room['battle_history'],
            'game_end_reason': '2勝先取' if max_score >= 2 else '3ラウンド終了',
            'room_id': room_id
        }
        
        print(f"DEBUG: Game ended with final scores: {game_end_data['final_scores']}")
        socketio.emit('game_finished', game_end_data, room=room_id)
        room['status'] = 'finished'
        
        auto_reset_cards_after_game(room_id)
        
    else:
        room['current_round'] += 1
        
        def start_next_round():
            socketio.emit('next_round', {
                'round': room['current_round'],
                'message': f'Round {room["current_round"]} 開始！',
                'room_id': room_id
            }, room=room_id)
        
        socketio.start_background_task(lambda: (
            socketio.sleep(3),
            start_next_round()
        ))

def auto_reset_cards_after_game(room_id):
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    
    for player_id, cards in room.get('player_cards', {}).items():
        for card in cards:
            if card.get('used', False):
                card['used'] = False

@socketio.on('request_rematch')
def handle_rematch(data):
    room_id = data['room_id'].upper()
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    # 現在のプレイヤーリストを取得
    players = room.get('players', [])
    
    # スコアを確実にリセット
    reset_scores = {}
    for player_id in players:
        reset_scores[player_id] = 0
    
    print(f"DEBUG: Rematch - resetting scores for players: {players}")
    print(f"DEBUG: Reset scores: {reset_scores}")
    
    room.update({
        'status': 'battle_ready',
        'current_round': 1,
        'scores': reset_scores,  # 確実にリセット
        'current_selections': {},
        'battle_history': []
    })
    
    # カードの使用状態もリセット
    for player_id, cards in room.get('player_cards', {}).items():
        for card in cards:
            card['used'] = False
    
    print(f"DEBUG: Rematch started with reset scores: {room['scores']}")
    
    socketio.emit('rematch_started', {
        'message': 'Rematch started! Round 1 begins.',
        'room_status': {
            'current_round': 1,
            'scores': room['scores'],
            'players': room['players']
        },
        'reset_cards': True
    }, room=room_id)

@socketio.on('reset_all_cards')
def handle_reset_all_cards(data):
    room_id = data['room_id'].upper()
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    reset_count = 0
    
    for player_id, cards in room.get('player_cards', {}).items():
        for card in cards:
            if card.get('used', False):
                card['used'] = False
                reset_count += 1
    
    for player_id, cards in room.get('player_cards', {}).items():
        socketio.emit('cards_reset', {
            'cards': cards,
            'message': f'{reset_count} cards have been reset',
            'reset_by': 'force_reset'
        }, room=player_id)

@socketio.on('request_card_sync')
def handle_card_sync_request(data):
    room_id = data['room_id'].upper()
    player_id = request.sid
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    if player_id in room.get('player_cards', {}):
        cards = room['player_cards'][player_id]
        emit('sync_card_status', {
            'cards': cards,
            'message': 'Card status synchronized on request',
            'timestamp': datetime.now().isoformat()
        })
    else:
        emit('error', {'message': 'No cards found for player'})

@socketio.on('force_card_update')
def handle_force_card_update(data):
    room_id = data['room_id'].upper()
    card_id = data['card_id']
    used_status = data['used']
    player_id = request.sid
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    
    if player_id in room.get('player_cards', {}):
        cards = room['player_cards'][player_id]
        for card in cards:
            if str(card['id']) == str(card_id):
                card['used'] = used_status
                
                socketio.emit('sync_card_status', {
                    'cards': cards,
                    'message': f'Card {card["name"]} force updated',
                    'force_update': True
                }, room=room_id)
                break
        else:
            emit('error', {'message': f'Card ID {card_id} not found'})
    else:
        emit('error', {'message': 'No cards found for player'})

@socketio.on('get_room_status')
def get_room_status(data):
    room_id = data.get('room_id', '').upper()
    
    if room_id in rooms:
        room = rooms[room_id]
        
        card_status = {}
        for player_id, cards in room.get('player_cards', {}).items():
            card_status[player_id] = {
                'total_cards': len(cards),
                'used_cards': sum(1 for card in cards if card.get('used', False)),
                'available_cards': sum(1 for card in cards if not card.get('used', False)),
                'card_details': [
                    {
                        'id': card.get('id'),
                        'name': card.get('name', 'Unknown'),
                        'used': card.get('used', False)
                    } for card in cards
                ]
            }
        
        emit('room_status', {
            'room_id': room_id,
            'status': room.get('status'),
            'current_round': room.get('current_round'),
            'players': room.get('players', []),
            'scores': room.get('scores', {}),
            'cards_ready': list(room.get('player_cards', {}).keys()),
            'card_status': card_status
        })
    else:
        emit('error', {'message': 'Room not found'})

@app.route('/cleanup-session/<session_id>', methods=['DELETE'])
def cleanup_session(session_id: str):
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
    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "localhost"
    
    local_ip = get_local_ip()
    port = 5000
    
    print("🎮 Photo Battle Full Stack Server")
    print("📋 Features:")
    print("   - HTML Pages: matching, card-generation, battle")
    print("   - Socket.IO: Real-time multiplayer")
    print("   - API: Card generation and image processing")
    print("   - Game Logic: Battle system with attribute effectiveness")
    print("🚀 Server starting...")
    print("🌐 Access URLs:")
    print(f"   - 自分のPC: http://localhost:{port}/")
    print(f"   - 同じWi-Fi内: http://{local_ip}:{port}/")
    print(f"   - スマホ: http://{local_ip}:{port}/")
    print("")
    print("📱 友達に共有するURL:")
    print(f"   http://{local_ip}:{port}/")
    print("")
    print("💡 友達のデバイスが同じWi-Fiに接続されていることを確認してください！")
    
    socketio.run(app, debug=False, host='0.0.0.0', port=port)