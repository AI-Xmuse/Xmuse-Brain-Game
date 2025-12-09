import pygame
import random
import time
from pythonosc import dispatcher
from pythonosc import osc_server
from threading import Thread, Event

# ------------------------------
# 1. 初始化与资源配置
# ------------------------------
pygame.init()
width, height = 700, 700
win = pygame.display.set_mode((width, height))
pygame.display.set_caption("Gomoku (Stable Control)")


# 生成游戏资源
def create_solid_image(size, color, alpha=255):
    img = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(img, (*color, alpha), (size // 2, size // 2), size // 2 - 1)
    return img


# 核心资源
bg_color = (245, 222, 179)
bg_img = pygame.Surface((width, height))
bg_img.fill(bg_color)
player_stone = create_solid_image(30, (0, 0, 0))  # 玩家黑棋
cpu_stone = create_solid_image(30, (255, 255, 255))  # 电脑白棋
cursor = create_solid_image(34, (255, 0, 0), 180)  # 半透红光标（定位更醒目）
score_bg = pygame.Surface((200, 50))
score_bg.fill((100, 100, 100))

# ------------------------------
# 2. 全局变量声明（新增控制稳定性参数）
# ------------------------------
# 棋盘配置
board_size = 15
grid_size = 40
offset_x = (width - (board_size - 1) * grid_size) // 2
offset_y = (height - (board_size - 1) * grid_size) // 2

# 游戏状态
board = [[0 for _ in range(board_size)] for _ in range(board_size)]  # 0空/1玩家/2电脑
current_turn = 1  # 1=玩家，2=电脑
player_score = 0
cpu_score = 0
game_over = False

# 头部控制参数（重点优化：提升稳定性）
cursor_pos = [7, 7]  # 初始光标在中心
move_threshold = 0.8  # 提高动作阈值（减少轻微晃动触发，默认0.6→0.8）
move_cooldown = 0.3  # 延长冷却时间（防连续抖动，默认0.2→0.3）
last_move_time = time.time()
last_osc_acc_time = time.time()  # 新增：OSC加速度信号接收冷却
osc_acc_cooldown = 0.05  # 加速度信号最小接收间隔（过滤高频噪声）

# 咬合落子参数（重点优化：防止误触发）
bite_triggered = False  # 新增：咬合动作触发标记（仅单次触发）
last_bite_time = time.time()
bite_cooldown = 1.0  # 咬合动作冷却（防止短时间内多次触发，默认0.5→1.0）

# 按钮与颜色
buttons = {
    "restart": pygame.Rect(width // 2 - 100, height // 2 - 50, 200, 50),
    "quit": pygame.Rect(width // 2 - 100, height // 2 + 20, 200, 50),
    "new_round": pygame.Rect(width // 2 - 100, height // 2 + 90, 200, 50)
}
colors = {
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "black": (0, 0, 0),
    "gray": (150, 150, 150),
    "green": (0, 200, 0)  # 新增：用于显示稳定状态提示
}

# 字体与文本（新增稳定性提示）
font = pygame.font.Font(None, 36)
font_large = pygame.font.Font(None, 72)
texts = {
    "restart": font.render("Restart", True, colors["white"]),
    "quit": font.render("Quit", True, colors["white"]),
    "new_round": font.render("New Round", True, colors["black"]),
    "player_turn": font.render("Your Turn (Move Head, Bite to Place)", True, colors["black"]),
    "cpu_turn": font.render("AI Thinking...", True, colors["black"]),
    "hint": font.render("Head Up/Down/Left/Right → Cursor | Bite Only to Place", True, colors["black"]),
    "stable_hint": font.render("Stable Mode: Reduced Sensitivity", True, colors["green"])  # 稳定模式提示
}

# OSC配置
ip = "127.0.0.1"
osc_prefix = ""
port = 5005  # 默认端口（可在输入界面修改）
stop_event = Event()

# 帧率控制
clock = pygame.time.Clock()


# ------------------------------
# 3. 高级AI核心逻辑（保持不变）
# ------------------------------
def reset_board(new_game=False):
    """重置棋盘状态"""
    global board, current_turn, game_over, cursor_pos, player_score, cpu_score, bite_triggered
    board = [[0 for _ in range(board_size)] for _ in range(board_size)]
    current_turn = 1
    game_over = False
    cursor_pos = [7, 7]
    bite_triggered = False  # 重置咬合触发标记
    if new_game:
        player_score = 0
        cpu_score = 0


def place_stone(x, y, player):
    """放置棋子并切换回合（仅在合法条件下执行）"""
    global game_over, player_score, cpu_score, current_turn
    # 双重校验：确保位置为空且游戏未结束
    if board[y][x] != 0 or game_over:
        print(f"Invalid Placement: Position ({x},{y}) is occupied or game over")
        return False

    board[y][x] = player
    # 检查获胜
    if check_win(x, y, player):
        game_over = True
        if player == 1:
            player_score += 1
        else:
            cpu_score += 1
        return True

    current_turn = 2 if current_turn == 1 else 1
    return True


def check_win(x, y, player):
    """检查是否五子连珠（四方向检测）"""
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for dx, dy in directions:
        count = 1
        # 正向延伸
        for i in range(1, 5):
            nx = x + dx * i
            ny = y + dy * i
            if 0 <= nx < board_size and 0 <= ny < board_size and board[ny][nx] == player:
                count += 1
            else:
                break
        # 反向延伸
        for i in range(1, 5):
            nx = x - dx * i
            ny = y - dy * i
            if 0 <= nx < board_size and 0 <= ny < board_size and board[ny][nx] == player:
                count += 1
            else:
                break
        if count >= 5:
            return True
    return False


# ------------------------------
# AI评分系统（保持不变）
# ------------------------------
def count_consecutive(x, y, dx, dy, player, empty_allowed=True):
    count = 0
    blocks = 0
    for i in range(1, 5):
        nx = x + dx * i
        ny = y + dy * i
        if 0 <= nx < board_size and 0 <= ny < board_size:
            if board[ny][nx] == player:
                count += 1
            elif board[ny][nx] == 0 and empty_allowed:
                break
            else:
                blocks += 1
                break
        else:
            blocks += 1
            break
    for i in range(1, 5):
        nx = x - dx * i
        ny = y - dy * i
        if 0 <= nx < board_size and 0 <= ny < board_size:
            if board[ny][nx] == player:
                count += 1
            elif board[ny][nx] == 0 and empty_allowed:
                break
            else:
                blocks += 1
                break
        else:
            blocks += 1
            break
    return count, blocks


def evaluate_position(x, y, player):
    if board[y][x] != 0:
        return -1
    max_score = 0
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for dx, dy in directions:
        consecutive, blocks = count_consecutive(x, y, dx, dy, player)
        total = consecutive + 1
        if total >= 5:
            score = 100000
        elif total == 4 and blocks == 0:
            score = 10000
        elif total == 4 and blocks == 1:
            score = 1000
        elif total == 3 and blocks == 0:
            score = 500
        elif total == 3 and blocks == 1:
            score = 100
        elif total == 2 and blocks == 0:
            score = 50
        elif total == 2 and blocks == 1:
            score = 10
        elif total == 1:
            score = 1
        else:
            score = 0
        if score > max_score:
            max_score = score
    return max_score


def advanced_ai_move():
    global current_turn, game_over
    if current_turn != 2 or game_over:
        return
    best_score = -1
    best_pos = None
    empty_cells = [(x, y) for x in range(board_size) for y in range(board_size) if board[y][x] == 0]
    for (x, y) in empty_cells:
        ai_score = evaluate_position(x, y, 2)
        player_score = evaluate_position(x, y, 1) * 1.1
        current_score = max(ai_score, player_score)
        center_dist = abs(x - 7) + abs(y - 7)
        if center_dist <= 3:
            current_score += 20
        if current_score > best_score:
            best_score = current_score
            best_pos = (x, y)
    if best_pos:
        x, y = best_pos
        place_stone(x, y, 2)


# ------------------------------
# 4. 头部动作与咬合信号处理（核心修复部分）
# ------------------------------
def head_move_handler(address, *args):
    """头部动作控制光标（优化稳定性：过滤噪声+防抖）"""
    global cursor_pos, last_move_time, current_turn, game_over, last_osc_acc_time
    # 多重校验：确保信号有效+玩家回合+游戏未结束
    if len(args) < 2 or current_turn != 1 or game_over:
        return

    current_time = time.time()
    # 1. OSC加速度信号接收冷却（过滤高频噪声，防止每秒接收过多信号）
    if current_time - last_osc_acc_time < osc_acc_cooldown:
        return
    last_osc_acc_time = current_time

    # 2. 光标移动冷却（防止连续抖动）
    if current_time - last_move_time < move_cooldown:
        return

    # 提取头部动作信号（仅使用有效范围的信号值，过滤异常值）
    head_y = max(min(args[0], 2.0), -2.0)  # 限制Y轴信号范围（-2.0~2.0）
    head_x = max(min(args[1], 2.0), -2.0)  # 限制X轴信号范围（-2.0~2.0）
    threshold = move_threshold

    # 上下控制（增加边界缓冲，避免光标贴边抖动）
    if head_y < -threshold and cursor_pos[1] > 0:
        cursor_pos[1] -= 1
        last_move_time = current_time
    elif head_y > threshold and cursor_pos[1] < board_size - 1:
        cursor_pos[1] += 1
        last_move_time = current_time

    # 左右控制（同上，增加边界缓冲）
    if head_x > threshold and cursor_pos[0] > 0:
        cursor_pos[0] -= 1
        last_move_time = current_time
    elif head_x < -threshold and cursor_pos[0] < board_size - 1:
        cursor_pos[0] += 1
        last_move_time = current_time


def bite_handler(address, *args):
    """咬合落子（修复自动落子：仅单次有效咬合触发）"""
    global last_bite_time, current_turn, game_over, cursor_pos, bite_triggered
    # 多重校验：确保信号有效+玩家回合+游戏未结束+未触发过
    if len(args) < 1 or current_turn != 1 or game_over or bite_triggered:
        return

    current_time = time.time()
    # 咬合冷却（防止短时间内多次触发）
    if current_time - last_bite_time < bite_cooldown:
        return

    # 仅当咬合信号为1（真实咬合动作）时触发
    if args[0] == 1:
        # 执行落子（额外校验光标位置是否为空）
        if board[cursor_pos[1]][cursor_pos[0]] == 0:
            if place_stone(cursor_pos[0], cursor_pos[1], 1):
                last_bite_time = current_time
                bite_triggered = True  # 标记为已触发，防止重复落子
                # 延迟1秒触发AI回合（模拟思考时间，避免AI秒落）
                pygame.time.set_timer(pygame.USEREVENT, 1000)
        else:
            print(f"Cannot Place: Position ({cursor_pos[0]},{cursor_pos[1]}) is occupied")


# ------------------------------
# 5. OSC服务器线程（增加异常捕获详细信息）
# ------------------------------
def osc_server_thread():
    try:
        osc_disp = dispatcher.Dispatcher()
        # 绑定OSC地址（确保与设备发送地址完全一致）
        osc_disp.map(f"{osc_prefix}/acc", head_move_handler)
        osc_disp.map(f"{osc_prefix}/elements/jaw_clench", bite_handler)
        server = osc_server.ThreadingOSCUDPServer((ip, port), osc_disp)
        print(f"OSC Server Running: {ip}:{port}")
        print("Waiting for Head Movement (acc) and Jaw Clench (jaw_clench) signals...")
        while not stop_event.is_set():
            server.handle_request()
    except Exception as e:
        # 打印详细错误信息，便于排查端口/地址问题
        print(f"\nOSC Error Details: {type(e).__name__}: {e}")
        print(f"Possible Fixes: 1. Change port (e.g., 5010) 2. Check OSC address match 3. Close occupied port")


# ------------------------------
# 6. 界面绘制（新增稳定性提示，优化光标显示）
# ------------------------------
def draw_board():
    """绘制棋盘、棋子、光标（光标显示更稳定）"""
    global board, cursor_pos, current_turn, game_over
    # 绘制网格（增加线条宽度，提升清晰度）
    for i in range(board_size):
        # 横线
        pygame.draw.line(win, colors["gray"],
                         (offset_x, offset_y + i * grid_size),
                         (offset_x + (board_size - 1) * grid_size, offset_y + i * grid_size), 3)
        # 竖线
        pygame.draw.line(win, colors["gray"],
                         (offset_x + i * grid_size, offset_y),
                         (offset_x + i * grid_size, offset_y + (board_size - 1) * grid_size), 3)

    # 绘制棋子（增加棋子边缘，提升区分度）
    for x in range(board_size):
        for y in range(board_size):
            if board[y][x] == 1:
                # 玩家棋子：黑棋+白色边缘
                pos = (offset_x + x * grid_size - 15, offset_y + y * grid_size - 15)
                pygame.draw.circle(win, colors["white"], (pos[0] + 15, pos[1] + 15), 15)  # 白色边缘
                win.blit(player_stone, pos)
            elif board[y][x] == 2:
                # 电脑棋子：白棋+黑色边缘
                pos = (offset_x + x * grid_size - 15, offset_y + y * grid_size - 15)
                pygame.draw.circle(win, colors["black"], (pos[0] + 15, pos[1] + 15), 15)  # 黑色边缘
                win.blit(cpu_stone, pos)

    # 绘制定位光标（仅玩家回合显示，增加闪烁效果提示当前位置）
    if current_turn == 1 and not game_over:
        cursor_pos_screen = (offset_x + cursor_pos[0] * grid_size - 17,
                             offset_y + cursor_pos[1] * grid_size - 17)
        # 光标闪烁效果（每0.5秒切换透明度，提升可见性）
        if int(time.time() * 2) % 2 == 0:
            win.blit(cursor, cursor_pos_screen)


def draw_ui():
    """绘制分数、回合提示、操作说明（新增稳定性提示）"""
    global player_score, cpu_score, current_turn, game_over, bite_triggered
    # 分数面板
    win.blit(score_bg, (20, 20))
    score_text = font.render(f"You: {player_score}  AI: {cpu_score}", True, colors["white"])
    win.blit(score_text, (30, 30))

    # 稳定模式提示（顶部左侧）
    win.blit(texts["stable_hint"], (20, height - 70))

    # 回合提示（顶部居中）
    if not game_over:
        if current_turn == 1:
            # 玩家回合：显示光标位置+咬合状态
            pos_text = font.render(f"Cursor: ({cursor_pos[0]},{cursor_pos[1]})", True, colors["red"])
            win.blit(pos_text, (width // 2 - 100, 50))
            if bite_triggered:
                bite_text = font.render("Bite Done! Waiting AI...", True, colors["green"])
                win.blit(bite_text, (width // 2 - 120, 80))
            else:
                win.blit(texts["player_turn"], (width // 2 - 220, 20))
        else:
            win.blit(texts["cpu_turn"], (width // 2 - 120, 20))

    # 操作提示（底部居中）
    win.blit(texts["hint"], (width // 2 - texts["hint"].get_width() // 2, height - 40))


def draw_game_over():
    """绘制游戏结束界面（重置咬合触发标记）"""
    global game_over, player_score, cpu_score, bite_triggered
    if not game_over:
        return

    bite_triggered = False  # 重置咬合标记，便于新回合使用
    # 获胜文本
    if player_score > cpu_score:
        result_text = font_large.render("You Win!", True, colors["red"])
    else:
        result_text = font_large.render("AI Wins!", True, colors["red"])
    win.blit(result_text, (width // 2 - result_text.get_width() // 2, height // 4))

    # 绘制按钮
    pygame.draw.rect(win, colors["red"], buttons["restart"])
    pygame.draw.rect(win, colors["black"], buttons["quit"])
    pygame.draw.rect(win, colors["white"], buttons["new_round"])
    win.blit(texts["restart"], (buttons["restart"].centerx - 40, buttons["restart"].centery - 18))
    win.blit(texts["quit"], (buttons["quit"].centerx - 25, buttons["quit"].centery - 18))
    win.blit(texts["new_round"], (buttons["new_round"].centerx - 60, buttons["new_round"].centery - 18))


# ------------------------------
# 7. OSC配置输入（优化提示，避免端口冲突）
# ------------------------------
def get_osc_prefix():
    input_text = ""
    input_active = True
    while input_active:
        win.fill(colors["black"])
        # 提示文本：说明前缀可跳过
        prompt = font.render("Enter OSC prefix (press Enter to skip, usually empty):", True, colors["white"])
        win.blit(prompt, (50, height // 3))
        input_surf = font.render(input_text, True, colors["white"])
        win.blit(input_surf, (50, height // 3 + 40))
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    input_active = False
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    input_text += event.unicode
    # 统一前缀格式（确保与设备发送格式一致）
    return input_text.strip().rstrip("/")  # 去除首尾空格和末尾斜杠


def get_port():
    input_text = ""
    input_active = True
    while input_active:
        win.fill(colors["black"])
        # 提示文本：推荐端口+冲突解决方案
        prompt = font.render(f"Enter port (default: {port}, try 5010 if 5005 is occupied):", True, colors["white"])
        win.blit(prompt, (50, height // 3))
        input_surf = font.render(input_text, True, colors["white"])
        win.blit(input_surf, (50, height // 3 + 40))
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    # 校验端口合法性（1024~65535）
                    if input_text.isdigit():
                        input_port = int(input_text)
                        if 1024 <= input_port <= 65535:
                            return input_port
                        else:
                            print("Port must be between 1024 and 65535, using default")
                    return port  # 非法输入使用默认端口
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.unicode.isdigit():
                    input_text += event.unicode
    return port


# ------------------------------
# 8. 主游戏循环（增加AI回合后重置咬合标记）
# ------------------------------
def game_loop():
    global osc_prefix, port, stop_event, bite_triggered
    # 获取OSC配置（前缀+端口）
    osc_prefix = get_osc_prefix()
    port = get_port()

    # 启动OSC线程（守护线程，主程序退出时自动关闭）
    osc_thread = Thread(target=osc_server_thread, daemon=True)
    osc_thread.start()

    # 初始化游戏
    reset_board(new_game=True)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                stop_event.set()

            # AI回合触发（触发后重置咬合标记）
            if event.type == pygame.USEREVENT:
                advanced_ai_move()
                bite_triggered = False  # 重置咬合标记，准备下一轮玩家回合
                pygame.time.set_timer(pygame.USEREVENT, 0)

            # 鼠标交互（备用控制，便于调试）
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                # 按钮点击
                if buttons["restart"].collidepoint(mx, my):
                    reset_board(new_game=True)
                elif buttons["quit"].collidepoint(mx, my):
                    running = False
                    stop_event.set()
                elif buttons["new_round"].collidepoint(mx, my):
                    reset_board()
                # 玩家回合：鼠标点击移动光标（调试用）
                elif current_turn == 1 and not game_over:
                    grid_x = (mx - offset_x) // grid_size
                    grid_y = (my - offset_y) // grid_size
                    if 0 <= grid_x < board_size and 0 <= grid_y < board_size:
                        cursor_pos[:] = [grid_x, grid_y]
                        print(f"Cursor moved to ({grid_x},{grid_y}) via mouse")

        # 界面绘制（顺序：背景→棋盘→UI→游戏结束）
        win.blit(bg_img, (0, 0))
        draw_board()
        draw_ui()
        draw_game_over()

        # 刷新屏幕+稳定帧率（15FPS，平衡流畅度与稳定性）
        pygame.display.update()
        clock.tick(15)

    # 退出清理
    stop_event.set()
    pygame.quit()
    print("\nGame Exited Normally")


# ------------------------------
# 启动游戏
# ------------------------------
if __name__ == "__main__":
    # 启动前提示：检查OSC设备连接
    print("=" * 50)
    print("Gomoku Game (Stable Control Version)")
    print("Before Starting:")
    print("1. Ensure OSC device is connected (e.g., Xmuse)")
    print("2. Set device OSC port to match game port (default 5005)")
    print("3. Send signals to addresses: /acc (head) and /elements/jaw_clench (bite)")
    print("=" * 50)
    game_loop()