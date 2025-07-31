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
OSC_address_prefix = ''
port_number = None  # 或者是默认值（根据你的需要）
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
        # 确保果实不在蛇身上
        if (x_fruit, y_fruit) not in zip(x_cor, y_cor):
            break
# 更新蛇的坐标
def update_snake_coordinates():
    global x_cor, y_cor
    # 保存当前蛇身的位置，用于更新
    prev_x = x_cor[:]
    prev_y = y_cor[:]
    # 更新蛇身，从尾部开始
    for i in range(num_segments - 1, 0, -1):  # 从尾部到蛇头前一节
        x_cor[i] = prev_x[i - 1]
        y_cor[i] = prev_y[i - 1]
    # 更新蛇头位置
    if direction == 'RIGHT':
        x_cor[0] += diff
    elif direction == 'LEFT':
        x_cor[0] -= diff
    elif direction == 'UP':
        y_cor[0] -= diff
    elif direction == 'DOWN':
        y_cor[0] += diff
    # 保证每一节蛇身的间隔
    for i in range(1, len(x_cor)):
        if direction == 'RIGHT':
            x_cor[i] = x_cor[i - 1] - 20  # 将身体部分沿着上一节的轨迹更新
        elif direction == 'LEFT':
            x_cor[i] = x_cor[i - 1] + 20
        elif direction == 'UP':
            y_cor[i] = y_cor[i - 1] + 20
        elif direction == 'DOWN':
            y_cor[i] = y_cor[i - 1] - 20


# 检查是否吃到果实
def check_for_fruit():
    global score, num_segments, diff
    if (x_cor[0] > x_fruit - 20 and x_cor[0] < x_fruit + 20 and y_cor[0] > y_fruit - 20 and y_cor[0] < y_fruit + 20):
        score += 1
        num_segments += 1  # 吃到果实时增加蛇身
        # 在蛇尾增加新的蛇身部分，并确保间隔为20像素
        x_cor.append(x_cor[-1])  # 将尾部增加一个位置
        y_cor.append(y_cor[-1])  # 将尾部增加一个位置
        # 新增的蛇尾部分坐标，间隔为20像素
        # 新增身体部分的坐标基于前一个身体部分（保持20像素间隔）
        x_cor[-1] = x_cor[-2] + 40  # 将新增身体部分与尾部保持20像素间隔
        y_cor[-1] = y_cor[-2]  # 保持同一高度
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


# 创建一个输入框来让用户输入OSC前缀
def get_osc_address_prefix():
    font = pygame.font.Font(None, 36)
    input_text = ''
    input_active = True
    user_input_done = False
    while input_active and not user_input_done:
        win.fill((0, 0, 0))  # 清空屏幕
        # 显示提示信息
        prompt_text = font.render("Please enter the OSC address prefix:", True, (255, 255, 255))
        win.blit(prompt_text, (50, height // 3))
        # 显示用户输入的内容
        input_surface = font.render(input_text, True, (255, 255, 255))
        win.blit(input_surface, (50, height // 3 + 40))
        # 刷新屏幕并处理事件
        pygame.display.update()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    user_input_done = True
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]  # 删除最后一个字符
                else:
                    input_text += event.unicode  # 添加字符
    return input_text

def get_port_number():
    font = pygame.font.Font(None, 36)
    input_text = ''
    input_active = True
    user_input_done = False

    while input_active and not user_input_done:
        win.fill((0, 0, 0))  # 清空屏幕
        # 显示提示信息
        prompt_text = font.render("Please enter the port number:", True, (255, 255, 255))
        win.blit(prompt_text, (50, height // 3))
        # 显示用户输入的内容
        input_surface = font.render(input_text, True, (255, 255, 255))
        win.blit(input_surface, (50, height // 3 + 40))
        # 刷新屏幕并处理事件
        pygame.display.update()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    user_input_done = True
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]  # 删除最后一个字符
                else:
                    input_text += event.unicode  # 添加字符
    return input_text



# 游戏结束时显示“Game Over”
def display_game_over():
    font = pygame.font.Font(None, 72)
    game_over_text = font.render("Game Over", True, red)
    win.blit(game_over_text, (width // 2 - game_over_text.get_width() // 2, height // 2))
    pygame.display.update()
    time.sleep(2)  # 显示2秒
    display_buttons()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = event.pos
                if restart_button.collidepoint(mouse_x, mouse_y):
                    game_loop()  # 点击重来按钮，重启游戏
                elif quit_button.collidepoint(mouse_x, mouse_y):
                    running = False  # 点击退出按钮，退出游戏
        pygame.display.update()
    pygame.quit()


def reset_game():
    global x_cor, y_cor, num_segments, direction, score, diff, x_fruit, y_fruit
    # 重置游戏变量
    x_cor = [width - 1]  # 初始蛇头位置
    y_cor = [250]  # 初始蛇头位置
    num_segments = 1  # 初始只有蛇头
    direction = 'LEFT'  # 初始方向
    score = 0  # 初始分数
    diff = 2  # 初始难度
    update_fruit_coordinates()  # 更新果实位置

def display_buttons():
    # 绘制按钮
    pygame.draw.rect(win, red, restart_button)  # 绘制重来按钮
    pygame.draw.rect(win, black, quit_button)  # 绘制退出按钮
    # 绘制按钮文本
    win.blit(restart_text, (width // 2 - restart_text.get_width() // 2, height // 2 - 40))
    win.blit(quit_text, (width // 2 - quit_text.get_width() // 2, height // 2 + 30))
    pygame.display.update()

def game_loop():
    global x_cor, y_cor, num_segments, direction, score, diff, x_fruit, y_fruit, OSC_address_prefix, port_number, port, address_prefix
    # 获取用户输入的OSC地址前缀
    OSC_address_prefix = get_osc_address_prefix()
    address_prefix = OSC_address_prefix
    port_number = int(get_port_number())  # 将端口号转换为整数
    port = port_number
    # 创建并启动OSC服务器线程
    osc_thread = Thread(target=osc_server_thread, args=(address_prefix, port))
    osc_thread.start()
    reset_game()  # 游戏开始前先重置游戏状态
    # 游戏主循环
    run_game = True
    while run_game:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run_game = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and direction != 'RIGHT':
                    direction = 'LEFT'
                if event.key == pygame.K_RIGHT and direction != 'LEFT':
                    direction = 'RIGHT'
                if event.key == pygame.K_UP and direction != 'DOWN':
                    direction = 'UP'
                if event.key == pygame.K_DOWN and direction != 'UP':
                    direction = 'DOWN'
        # 更新游戏状态
        update_snake_coordinates()
        # 检查是否碰到边界
        if x_cor[0] < 0 or x_cor[0] >= width or y_cor[0] < 0 or y_cor[0] >= height:
            display_game_over()  # 游戏结束，显示Game Over
        check_for_fruit()
        # 绘制游戏界面
        win.blit(bg_img, (0, 0))  # 绘制背景
        for i in range(num_segments):
            if i == 0:  # 绘制蛇头
                win.blit(rotate_head(direction, img_head), (x_cor[i], y_cor[i]))
            else:  # 绘制蛇身
                win.blit(img_body, (x_cor[i], y_cor[i]))
        win.blit(img_ball, (x_fruit, y_fruit))  # 绘制果实
        # 绘制分数背景
        win.blit(img_score_bg, (10, 10))
        score_text = pygame.font.Font(None, 36).render(f"Score: {score}", True, (255, 255, 255))
        win.blit(score_text, (60, 20))
        pygame.display.update()
        clock.tick(15)  # 控制游戏帧率



if __name__ == "__main__":
    game_loop()
    pygame.quit()
