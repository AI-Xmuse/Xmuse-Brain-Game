import pygame
import numpy as np
from pythonosc import dispatcher
from pythonosc import osc_server
from threading import Thread, Event
import time

# ===================== 可调参数区 =====================
move_speed_ratio = 1.8
blink_threshold = 0.5
emg_threshold = 0.5
buffer_len = 3
deadzone = 0.12
interp_factor = 0.3
max_speed = 15.0
return_delay = 0.6
return_speed = 0.03
filter_window = 10
debounce_duration = 0.15
# OSC配置（XMuse Direct输出到端口7000）
OSC_HOST = "127.0.0.1"
OSC_PORT = 7000
# ======================================================

# 全局信号缓存
tilt_buffer = np.zeros(filter_window)
current_tilt_y = 0.0
target_tilt_y = 0.0
last_active_tilt = 0.0
last_active_time = time.time()
last_direction_change_time = time.time()
last_stable_tilt = 0.0
eeg_blink_buf = np.zeros(buffer_len)
emg_clench_buf = np.zeros(buffer_len)

# 防抖参数
last_blink_time = time.time()
blink_cooldown = 0.5
last_bite_time = time.time()
bite_cooldown = 1.0
game_start_time = time.time()
start_delay = 1.0

stop_event = Event()

def osc_acc_handler(unused_addr, *args):
    global current_tilt_y, target_tilt_y, tilt_buffer
    if len(args) >= 3:
        x, y, z = args[0], args[1], args[2]
        tilt_buffer = np.roll(tilt_buffer, -1)
        tilt_buffer[-1] = y
        target_tilt_y = np.mean(tilt_buffer)
        print(f"ACC: x={x:.2f}, y={y:.2f}, z={z:.2f}")

def osc_blink_handler(unused_addr, *args):
    global eeg_blink_buf
    if len(args) >= 1:
        eeg_blink_buf = np.roll(eeg_blink_buf, -1)
        eeg_blink_buf[-1] = args[0]
        print(f"Blink: {args[0]}")

def osc_jaw_clench_handler(unused_addr, *args):
    global emg_clench_buf
    if len(args) >= 1:
        emg_clench_buf = np.roll(emg_clench_buf, -1)
        emg_clench_buf[-1] = args[0]
        print(f"Jaw Clench: {args[0]}")

def default_handler(unused_addr, *args):
    pass

def start_osc_server():
    disp = dispatcher.Dispatcher()
    disp.map("/*/acc", osc_acc_handler)
    disp.map("/*/elements/blink", osc_blink_handler)
    disp.map("/*/elements/jaw_clench", osc_jaw_clench_handler)
    disp.set_default_handler(default_handler)
    
    server = osc_server.BlockingOSCUDPServer((OSC_HOST, OSC_PORT), disp)
    print(f"OSC服务器已启动，监听 {OSC_HOST}:{OSC_PORT}")
    server.serve_forever()

osc_thread = Thread(target=start_osc_server)
osc_thread.daemon = True
osc_thread.start()

# ===================== Pygame打砖块游戏逻辑 =====================
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("XMuse OSC脑控打砖块")
clock = pygame.time.Clock()
FPS = 60

WHITE = (255,255,255)
GREEN = (0,255,0)
RED = (255,0,0)
BLACK = (0,0,0)

paddle_w, paddle_h = 120, 18
paddle_x = WIDTH//2 - paddle_w//2
paddle_y = HEIGHT - 40

ball_r = 10
ball_x, ball_y = paddle_x + paddle_w//2, paddle_y - ball_r
ball_vx, ball_vy = 0, 0
ball_on_paddle = True

brick_rows = 6
brick_cols = 10
brick_w = WIDTH // brick_cols - 4
brick_h = 22
bricks = []
for row in range(brick_rows):
    for col in range(brick_cols):
        bx = col * (brick_w + 4) + 2
        by = row * (brick_h + 4) + 30
        bricks.append(pygame.Rect(bx, by, brick_w, brick_h))

game_running = True
while game_running:
    screen.fill(BLACK)
    clock.tick(FPS)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            game_running = False

    # 1. 头部倾斜控制挡板位置（使用y轴，左右摇头）
    current_tilt_y += (target_tilt_y - current_tilt_y) * 0.5
    
    tilt_input = current_tilt_y
    current_time = time.time()
    direction_changed = False
    
    if tilt_input * last_stable_tilt < 0 and abs(tilt_input) > deadzone and abs(last_stable_tilt) > deadzone:
        direction_changed = True
    
    if abs(tilt_input) > deadzone:
        if direction_changed and current_time - last_direction_change_time < debounce_duration:
            tilt_input = last_stable_tilt
        else:
            last_stable_tilt = tilt_input
            last_direction_change_time = current_time
        
        last_active_tilt = tilt_input
        last_active_time = current_time
        target_paddle_x = (WIDTH - paddle_w) * (0.5 + tilt_input * move_speed_ratio)
    else:
        if current_time - last_active_time > return_delay:
            center_x = (WIDTH - paddle_w) * 0.5
            target_paddle_x = paddle_x + (center_x - paddle_x) * return_speed
        else:
            target_paddle_x = (WIDTH - paddle_w) * (0.5 + last_active_tilt * move_speed_ratio)
    
    move_step = (target_paddle_x - paddle_x) * interp_factor
    move_step = max(-max_speed, min(max_speed, move_step))
    paddle_x += move_step
    paddle_x = max(0, min(WIDTH - paddle_w, paddle_x))

    # 2. 眨眼检测：发射小球
    current_time = time.time()
    smooth_blink = np.mean(eeg_blink_buf)
    if current_time - game_start_time > start_delay:
        if smooth_blink > blink_threshold and ball_on_paddle and (current_time - last_blink_time > blink_cooldown):
            ball_vx = 6 if current_tilt_y > 0 else -6
            ball_vy = -6
            ball_on_paddle = False
            last_blink_time = current_time
            eeg_blink_buf = np.zeros(buffer_len)
            print("眨眼检测到！小球发射！")

    # 3. 咬牙检测：小球加速
    smooth_emg = np.mean(emg_clench_buf)
    if smooth_emg > emg_threshold and not ball_on_paddle and (current_time - last_bite_time > bite_cooldown):
        ball_vx *= 1.15
        ball_vy *= 1.15
        last_bite_time = current_time
        print("咬牙检测到！小球加速！")

    # 小球运动逻辑
    if not ball_on_paddle:
        ball_x += ball_vx
        ball_y += ball_vy
        if ball_x <= ball_r or ball_x >= WIDTH - ball_r:
            ball_vx *= -1
        if ball_y <= ball_r:
            ball_vy *= -1
        if ball_y > HEIGHT:
            ball_x, ball_y = paddle_x + paddle_w//2, paddle_y - ball_r
            ball_vx, ball_vy = 0, 0
            ball_on_paddle = True
            last_blink_time = time.time()
            eeg_blink_buf = np.zeros(buffer_len)
            print("球掉落！等待新的眨眼...")

    # 砖块碰撞检测
    ball_rect = pygame.Rect(ball_x-ball_r, ball_y-ball_r, ball_r*2, ball_r*2)
    hit_idx = ball_rect.collidelist(bricks)
    if hit_idx != -1:
        del bricks[hit_idx]
        ball_vy *= -1
        if len(bricks) == 0:
            print("恭喜通关！")
            pygame.time.wait(2000)
            game_running = False

    # 挡板碰撞
    paddle_rect = pygame.Rect(paddle_x, paddle_y, paddle_w, paddle_h)
    if ball_rect.colliderect(paddle_rect) and ball_vy > 0:
        ball_vy *= -1
        offset = (ball_x - (paddle_x + paddle_w//2)) / (paddle_w//2)
        ball_vx = offset * 7

    if ball_on_paddle:
        ball_x = paddle_x + paddle_w//2

    pygame.draw.rect(screen, GREEN, paddle_rect)
    pygame.draw.circle(screen, WHITE, (int(ball_x), int(ball_y)), ball_r)
    for b in bricks:
        pygame.draw.rect(screen, RED, b)

    pygame.display.flip()

pygame.quit()