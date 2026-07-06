import pygame
import random
import time
from pythonosc import dispatcher
from pythonosc import osc_server
from threading import Thread, Event

# 初始化游戏
pygame.init()
width, height = 700, 700
win = pygame.display.set_mode((width, height))
pygame.display.set_caption("Snake Game")
# 加载背景和果实图像
bg_img = pygame.image.load("bg_snake_02.png")  # 背景图像
bg_img = pygame.transform.scale(bg_img, (width, height))  # 调整背景大小
img_ball = pygame.image.load("img_ball.png")  # 新的果实图标
img_ball = pygame.transform.scale(img_ball, (20, 20))  # 调整果实图标大小
# 加载分数背景图像
img_score_bg = pygame.image.load("img_score.png")  # 分数背景图像
img_score_bg = pygame.transform.scale(img_score_bg, (150, 50))  # 调整为适合显示分数的大小
# 加载蛇头和蛇身图像
img_head = pygame.image.load("img_head_right.png")  # 蛇头图像
img_head = pygame.transform.scale(img_head, (20, 20))  # 调整蛇头图像大小
img_body = pygame.image.load("body_1.png")  # 蛇身图像
img_body = pygame.transform.scale(img_body, (20, 20))  # 调整蛇身图像大小
# 初始化游戏变量
num_segments = 1  # 初始只有一个蛇头
direction = 'LEFT'
x_start = width - 1
y_start = 250
score = 0
diff = 2  # 初始diff为2
x_cor = [x_start]  # 设置蛇的起始位置，只包含蛇头
y_cor = [y_start]
x_fruit, y_fruit = 250, 250
head_trail = [(x_start, y_start)]  # 蛇头轨迹（身体跟随用）
# 颜色定义
white = (255, 255, 255)
red = (255, 0, 0)
black = (0, 0, 0)
# 设置按钮
restart_button = pygame.Rect(width // 2 - 100, height // 2 - 50, 200, 50)
quit_button = pygame.Rect(width // 2 - 100, height // 2 + 20, 200, 50)
# 创建字体
font = pygame.font.Font(None, 36)
restart_text = font.render("Restart", True, white)
quit_text = font.render("Quit", True, white)

# OSC设置
ip = "127.0.0.1"
OSC_address_prefix = "/hab"
port = 7000
stop_event = Event()
acc_data = {'x': [], 'y': [], 'z': [], 'timestamps': []}
sampling_time = 2.0  # 采样时间，单位为秒
last_action_time = time.time()  # 上次动作检测的时间
cooldown_period = 2  # 冷却时间为2秒
# 设置帧率
clock = pygame.time.Clock()
# 更新果实坐标，确保果实生成在地图较为中间的随机位置
def update_fruit_coordinates():
    global x_fruit, y_fruit
    margin = 40  # 定义距离边缘的最小距离，避免果实出现在边缘
    # 设置果实生成的中心区域范围，限定在地图宽度和高度的40%到60%之间
    center_x_range = (width * 0.3, width * 0.7)
    center_y_range = (height * 0.3, height * 0.7)
    while True:
        # 在中心区域范围内随机生成果实位置
        x_fruit = random.randint(center_x_range[0] // 10 * 10, center_x_range[1] // 10 * 10)
        y_fruit = random.randint(center_y_range[0] // 10 * 10, center_y_range[1] // 10 * 10)
        # 确保果实不在蛇身上（距离检测，兼容插值坐标）
        overlap = False
        for sx, sy in zip(x_cor, y_cor):
            if abs(x_fruit - sx) < 20 and abs(y_fruit - sy) < 20:
                overlap = True
                break
        if not overlap:
            break
# 更新蛇的坐标（轨迹跟随，身体自然弯曲）
def update_snake_coordinates():
    global x_cor, y_cor, head_trail
    # 记录当前蛇头位置到轨迹
    head_trail.append((x_cor[0], y_cor[0]))
    max_trail = num_segments * 30 + 200
    if len(head_trail) > max_trail:
        head_trail = head_trail[-max_trail:]
    # 蛇头按方向移动
    if direction == 'RIGHT':
        x_cor[0] += diff
    elif direction == 'LEFT':
        x_cor[0] -= diff
    elif direction == 'UP':
        y_cor[0] -= diff
    elif direction == 'DOWN':
        y_cor[0] += diff
    # 身体各段从轨迹中取位置（段间距20px）
    for i in range(1, num_segments):
        target_dist = i * 20
        traveled = 0.0
        found = False
        for j in range(len(head_trail) - 1, 0, -1):
            dx = head_trail[j][0] - head_trail[j - 1][0]
            dy = head_trail[j][1] - head_trail[j - 1][1]
            step = (dx * dx + dy * dy) ** 0.5
            if traveled + step >= target_dist:
                ratio = (target_dist - traveled) / step if step > 0 else 0
                x_cor[i] = head_trail[j - 1][0] + dx * (1 - ratio)
                y_cor[i] = head_trail[j - 1][1] + dy * (1 - ratio)
                found = True
                break
            traveled += step
        if not found and head_trail:
            x_cor[i], y_cor[i] = head_trail[0]


# 检查是否吃到果实
def check_for_fruit():
    global score, num_segments, diff
    if (x_cor[0] > x_fruit - 20 and x_cor[0] < x_fruit + 20 and y_cor[0] > y_fruit - 20 and y_cor[0] < y_fruit + 20):
        score += 1
        num_segments += 1
        # 新身体段从轨迹末尾取位置（自动保持20px间距）
        if len(head_trail) >= num_segments * 10:
            x_cor.append(head_trail[-num_segments * 10][0])
            y_cor.append(head_trail[-num_segments * 10][1])
        else:
            x_cor.append(x_cor[-1])
            y_cor.append(y_cor[-1])
        update_fruit_coordinates()
        # 每当score增加5时，diff增加1
        if score % 5 == 0:
            diff += 1
            print(f"Difficulty increased! New diff value: {diff}")

# 处理加速度数
def acc_handler(address, *args):
    global last_action_time, direction
    current_time = time.time()
    # 限制接收频率
    if current_time - last_action_time < 0.1:
        return
    # 根据采样时间移除旧的数据点
    check_action_conditions(args[0], args[1], current_time)  # 直接传递acc_1、acc_2以及当前时间
def jaw_clench_handler(address, *args):
    global last_action_time, x_fruit, y_fruit, direction, score
    jaw_clench_value = args[0]  # 获取传递的值（0 或 1）
    if jaw_clench_value == 1:
        update_fruit_coordinates()  # 如果 jaw_clench 为 1，重新生成果实
# 根据接收到的加速度数据判断动作
def check_action_conditions(acc_1, acc_2, current_time):
    global last_action_time, direction
    # 判定方向
    if acc_1 < -0.75:
        if current_time - last_action_time > cooldown_period and direction != 'DOWN':
            direction = 'UP'
            last_action_time = current_time
    elif acc_1 > 0.1:
        if current_time - last_action_time > cooldown_period and direction != 'UP':
            direction = 'DOWN'
            last_action_time = current_time
    elif acc_2 < -0.5:
        if current_time - last_action_time > cooldown_period and direction != 'RIGHT':
            direction = 'LEFT'
            last_action_time = current_time
    elif acc_2 > 0.5:
        if current_time - last_action_time > cooldown_period and direction != 'LEFT':
            direction = 'RIGHT'
            last_action_time = current_time

# OSC服务器线程
def osc_server_thread(address_prefix, port):
    osc_dispatcher = dispatcher.Dispatcher()
    # 映射 acc 和 jaw_clench 地址
    osc_dispatcher.map(f"{address_prefix}/acc", acc_handler)
    osc_dispatcher.map(f"{address_prefix}/elements/jaw_clench", jaw_clench_handler)  # 处理 jaw_clench
    server = osc_server.ThreadingOSCUDPServer((ip, port), osc_dispatcher)
    server.serve_forever()
# 根据方向旋转蛇头图像
def rotate_head(direction, img_head):
    if direction == 'UP':
        return pygame.transform.rotate(img_head, 90)
    elif direction == 'DOWN':
        return pygame.transform.rotate(img_head, -90)
    elif direction == 'LEFT':
        return pygame.transform.rotate(img_head, 180)
    return img_head


# ── 通用文本输入（TEXTINPUT 兼容中文输入法）──
def text_input_screen(title, default, validator=None):
    input_text = default
    active = True
    pygame.key.start_text_input()

    while active:
        win.fill((0, 0, 0))
        prompt = font.render(title, True, white)
        win.blit(prompt, (50, height // 3 - 10))
        box_rect = pygame.Rect(50, height // 3 + 30, width - 100, 40)
        pygame.draw.rect(win, (60, 60, 60), box_rect)
        pygame.draw.rect(win, (0, 200, 0), box_rect, 2)
        cursor = "|" if int(time.time() * 2) % 2 == 0 else ""
        surf = font.render(input_text + cursor, True, white)
        win.blit(surf, (60, height // 3 + 38))
        hint = font.render("Enter=Confirm  Backspace=Delete  Esc=Use Default", True, (150, 150, 150))
        win.blit(hint, (50, height // 3 + 85))
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.TEXTINPUT:
                input_text += event.text
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    active = False
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.key == pygame.K_ESCAPE:
                    input_text = default
                    active = False

    pygame.key.stop_text_input()
    if validator:
        return validator(input_text)
    return input_text.strip().rstrip("/")


def validate_prefix(text):
    return text.strip().rstrip("/")


def validate_port(text):
    if text.isdigit():
        p = int(text)
        if 1024 <= p <= 65535:
            return p
    return port



# 游戏结束时显示“Game Over”
def display_game_over():
    """显示结束界面，返回 "restart" 或 "quit" """
    font = pygame.font.Font(None, 72)
    game_over_text = font.render("Game Over", True, red)
    win.blit(game_over_text, (width // 2 - game_over_text.get_width() // 2, height // 2))
    pygame.display.update()
    time.sleep(2)
    display_buttons()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = event.pos
                if restart_button.collidepoint(mouse_x, mouse_y):
                    return "restart"
                elif quit_button.collidepoint(mouse_x, mouse_y):
                    return "quit"
        pygame.display.update()


def reset_game():
    global x_cor, y_cor, num_segments, direction, score, diff, x_fruit, y_fruit, head_trail
    x_cor = [width - 1]
    y_cor = [250]
    num_segments = 1
    direction = 'LEFT'
    score = 0
    diff = 2
    head_trail = [(x_cor[0], y_cor[0])]
    update_fruit_coordinates()

def display_buttons():
    # 绘制按钮
    pygame.draw.rect(win, red, restart_button)  # 绘制重来按钮
    pygame.draw.rect(win, black, quit_button)  # 绘制退出按钮
    # 绘制按钮文本
    win.blit(restart_text, (width // 2 - restart_text.get_width() // 2, height // 2 - 40))
    win.blit(quit_text, (width // 2 - quit_text.get_width() // 2, height // 2 + 30))
    pygame.display.update()

def game_loop():
    global x_cor, y_cor, num_segments, direction, score, diff, x_fruit, y_fruit, OSC_address_prefix, port, stop_event
    OSC_address_prefix = text_input_screen(
        "Enter OSC prefix (e.g. /hab):", "/hab", validate_prefix)
    port = text_input_screen(
        "Enter OSC port (1024-65535):", str(port), validate_port)
    stop_event.clear()
    osc_thread = Thread(target=osc_server_thread, args=(OSC_address_prefix, port), daemon=True)
    osc_thread.start()

    while True:
        reset_game()
        run_game = True
        while run_game:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_event.set()
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT and direction != 'RIGHT':
                        direction = 'LEFT'
                    if event.key == pygame.K_RIGHT and direction != 'LEFT':
                        direction = 'RIGHT'
                    if event.key == pygame.K_UP and direction != 'DOWN':
                        direction = 'UP'
                    if event.key == pygame.K_DOWN and direction != 'UP':
                        direction = 'DOWN'
            update_snake_coordinates()
            # 碰壁 → 游戏结束
            if x_cor[0] < 0 or x_cor[0] >= width or y_cor[0] < 0 or y_cor[0] >= height:
                action = display_game_over()
                if action == "quit":
                    stop_event.set()
                    return
                else:  # restart
                    reset_game()
                    break
            check_for_fruit()
            # 绘制
            win.blit(bg_img, (0, 0))
            for i in range(num_segments):
                if i == 0:
                    win.blit(rotate_head(direction, img_head), (x_cor[i], y_cor[i]))
                else:
                    win.blit(img_body, (x_cor[i], y_cor[i]))
            win.blit(img_ball, (x_fruit, y_fruit))
            win.blit(img_score_bg, (10, 10))
            score_text = pygame.font.Font(None, 36).render(f"Score: {score}", True, (255, 255, 255))
            win.blit(score_text, (60, 20))
            pygame.display.update()
            clock.tick(15)



if __name__ == "__main__":
    game_loop()
    pygame.quit()
