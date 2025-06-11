from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 一時的なデータストレージ（後でDBに置き換え）
rooms = {}
users = {}

@app.route('/')
def index():
    return render_template('index.html')

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