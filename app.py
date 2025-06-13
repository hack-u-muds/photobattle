from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
from card_generator import CardGenerator
import base64
from io import BytesIO


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 一時的なデータストレージ（後でDBに置き換え）
rooms = {}
users = {}

@app.route('/')
def index():
    return render_template('index.html')

# カード生成用のインスタンス
card_generator = CardGenerator()

@app.route('/upload', methods=['POST'])
def upload_photos():
    """写真アップロードとカード生成"""
    if 'photos' not in request.files:
        return {'error': 'No photos uploaded'}, 400
    
    photos = request.files.getlist('photos')
    if len(photos) != 3:
        return {'error': 'Exactly 3 photos required'}, 400
    
    user_id = request.sid
    cards_info = []
    
    for i, photo in enumerate(photos):
        # 一時保存
        temp_path = f"temp_{user_id}_{i}.jpg"
        photo.save(temp_path)
        
        # カード生成
        card_path = f"cards/{user_id}_card_{i}.png"
        card_info = card_generator.generate_card(temp_path, card_path)
        
        # カード画像をBase64エンコード
        with open(card_path, 'rb') as f:
            card_base64 = base64.b64encode(f.read()).decode()
        
        cards_info.append({
            'id': i,
            'power': card_info['power'],
            'attribute': assign_attribute(card_info['features']),
            'image': card_base64,
            'used': False
        })
        
        # 一時ファイル削除
        os.remove(temp_path)
    
    # ユーザーのカード情報を保存
    users[user_id] = {'cards': cards_info}
    
    return {'cards': cards_info}

# ゲーム状態管理の拡張
rooms = {
    # room_id: {
    #     'players': [sid1, sid2],
    #     'status': 'waiting'|'card_selection'|'battle'|'finished',
    #     'current_round': 0,
    #     'rounds': [],  # 各ラウンドの結果
    #     'scores': {'player1': 0, 'player2': 0}
    # }
}

def assign_attribute(features):
    """特徴量から属性を決定"""
    if features['color_diversity'] > 0.7:
        return 'fire'
    elif features['complexity'] > 0.6:
        return 'earth'
    elif features['contrast'] > 0.5:
        return 'water'
    else:
        return 'air'

def calculate_battle_power(base_power, my_attr, opponent_attr):
    """属性相性を考慮した攻撃力計算"""
    multipliers = {
        ('fire', 'earth'): 1.2,
        ('earth', 'water'): 1.2,
        ('water', 'air'): 1.2,
        ('air', 'fire'): 1.2,
        # 逆相性
        ('earth', 'fire'): 0.8,
        ('water', 'earth'): 0.8,
        ('air', 'water'): 0.8,
        ('fire', 'air'): 0.8
    }
    
    multiplier = multipliers.get((my_attr, opponent_attr), 1.0)
    return int(base_power * multiplier)

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
    
    # カードが使用済みでないか確認
    user_cards = users[user_id]['cards']
    selected_card = next((c for c in user_cards if c['id'] == card_id), None)
    
    if not selected_card or selected_card['used']:
        emit('error', {'message': 'Invalid card selection'})
        return
    
    # ラウンド情報に選択を記録
    if 'current_selections' not in room:
        room['current_selections'] = {}
    
    room['current_selections'][user_id] = {
        'card': selected_card,
        'player_id': user_id
    }
    
    # 両プレイヤーが選択完了したら戦闘処理
    if len(room['current_selections']) == 2:
        process_battle(room_id)

def process_battle(room_id):
    """戦闘処理"""
    room = rooms[room_id]
    selections = room['current_selections']
    
    players = list(selections.keys())
    player1, player2 = players[0], players[1]
    
    card1 = selections[player1]['card']
    card2 = selections[player2]['card']
    
    # 属性相性を考慮した攻撃力計算
    power1 = calculate_battle_power(card1['power'], card1['attribute'], card2['attribute'])
    power2 = calculate_battle_power(card2['power'], card2['attribute'], card1['attribute'])
    
    # 勝敗判定
    if power1 > power2:
        winner = player1
        loser = player2
    elif power2 > power1:
        winner = player2
        loser = player1
    else:
        winner = None  # 引き分け
    
    # スコア更新
    if winner:
        room['scores'][winner] = room['scores'].get(winner, 0) + 1
    
    # カードを使用済みに
    users[player1]['cards'][card1['id']]['used'] = True
    users[player2]['cards'][card2['id']]['used'] = True
    
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
    if room['scores'].get(player1, 0) >= 2 or room['scores'].get(player2, 0) >= 2:
        final_winner = player1 if room['scores'].get(player1, 0) >= 2 else player2
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


@socketio.on('connect')
def on_connect():
    print(f'Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to server'})

@socketio.on('disconnect')
def on_disconnect():
    print(f'Client disconnected: {request.sid}')

@socketio.on('create_room')
def create_room():
    room_id = str(uuid.uuid4())[:8]
    rooms[room_id] = {
        'players': [],
        'status': 'waiting',
        'current_round': 0
    }
    join_room(room_id)
    rooms[room_id]['players'].append(request.sid)
    
    emit('room_created', {
        'room_id': room_id,
        'message': f'Room {room_id} created successfully'
    })

@socketio.on('join_room_request')
def join_room_request(data):
    room_id = data['room_id']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    if len(rooms[room_id]['players']) >= 2:
        emit('error', {'message': 'Room is full'})
        return
    
    join_room(room_id)
    rooms[room_id]['players'].append(request.sid)
    
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

@socketio.on('test_message')
def handle_test_message(data):
    print(f'Received test message: {data}')
    emit('test_response', {'message': f'Server received: {data["message"]}'})

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)