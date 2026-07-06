import pygame
import random
from pythonosc import dispatcher, osc_server
import threading
import time

# 初始化Pygame
pygame.init()
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 800
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("TANK BATTLE")
WALL_SIZE = 40


# 图像加载容错函数
def load_image(path, size=None):
    try:
        img = pygame.image.load(path).convert_alpha()  # 增加alpha通道支持
        if size:
            img = pygame.transform.scale(img, size)
        return img
    except FileNotFoundError:
        print(f"警告：未找到图像文件 {path}，使用默认图形替代")
        surf = pygame.Surface(size if size else (40, 40))
        surf.fill((100, 100, 100))  # 灰色替代
        return surf


# 加载游戏资源
bg_img = load_image("bottom-photo.png", (SCREEN_WIDTH, SCREEN_HEIGHT))
img_df_tank = load_image("perjure2.png", (40, 40))
img_score_bg = load_image("img_score.png", (150, 50))
img_tank_head = load_image("zhujue1.png", (40, 40))

# 加载子弹图片（提前加载避免重复IO操作）
player_bullet_img = load_image("bullet1.png", (10, 10))
enemy_bullet_img = load_image("bullet1.png", (10, 10))  # 可以替换为不同的敌人子弹图片

breakable_wall_img = load_image("wall_pic.png", (WALL_SIZE, WALL_SIZE))  # 可破坏墙壁图片
unbreakable_wall_img = load_image("wall_pic2.png", (WALL_SIZE, WALL_SIZE))  # 不可破坏墙壁图片

# 游戏常量
TANK_SIZE = 40
BULLET_SIZE = 10
FPS = 50
PLAYER_SHOOT_COOLDOWN = 1.0  # 玩家射击冷却时间
ENEMY_SHOOT_PROBABILITY = 0.005  # 敌人射击概率
ENEMY_MAX_COUNT = 3  # 最大敌人数量

# 颜色定义
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
GRAY = (100, 100, 100)
YELLOW = (255, 255, 0)
BLUE = (0, 0, 255)

# 按钮设置
restart_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 - 50, 200, 50)
quit_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 20, 200, 50)
start_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT // 2 + 50, 200, 50)

# 字体设置
try:
    font = pygame.font.Font("font.ttf", 36)  # 尝试加载自定义字体
except:
    font = pygame.font.Font(None, 36)  # 失败则使用默认字体
small_font = pygame.font.Font(None, 24)

restart_text = font.render("Restart", True, WHITE)
quit_text = font.render("Quit", True, WHITE)
start_text = font.render("Start Game", True, WHITE)
title_text = font.render("TANK BATTLE", True, YELLOW)

# OSC设置
ip = "127.0.0.1"
OSC_address_prefix = "/hab"
port = 7000
global_osc_server = None
eeg_lock = threading.Lock()
eeg_commands = {
    "left_eyebrow": False,
    "right_eyebrow": False,
    "clench_teeth": False,
    "blink": False,
    "forward_end_time": 0,  # 前进结束时间
    "last_clench_time": 0
}


# OSC回调函数
def eeg_handler(address, *args):
    global eeg_commands
    if not args:
        return

    value = args[0]
    current_time = time.time()  # 获取当前时间戳（秒）
    with eeg_lock:
        if address.endswith("eeg/eeg[0]"):
            eeg_commands["left_eyebrow"] = value > 0.001
        elif address.endswith("jaw_clench"):
            if value > 0.99:  # 检测到有效咬牙信号
                # 计算当前时间与上次咬牙的间隔
                time_since_last = current_time - eeg_commands["last_clench_time"]
                if time_since_last > 0.8:  # 间隔超过1秒，才更新状态
                    eeg_commands["right_eyebrow"] = True  # 原咬牙对应的状态（根据你的代码逻辑）
                    eeg_commands["last_clench_time"] = current_time  # 记录本次时间
                else:
                    # 信号无效时，重置状态（避免一直处于“咬牙”状态）
                    eeg_commands["right_eyebrow"] = False
            else:
                # 无论是否在冷却，信号消失就重置状态
                eeg_commands["right_eyebrow"] = False
        elif address.endswith("blink"):
            if value > 0.7:
                eeg_commands["forward_end_time"] = time.time() + 0.2
        elif address.endswith("touching_forehead"):
            eeg_commands["blink"] = value > 0.9999

# OSC服务器线程
def osc_server_thread(address_prefix, port):
    global global_osc_server
    pfx = address_prefix.rstrip("/")
    osc_dispatcher = dispatcher.Dispatcher()
    osc_dispatcher.map(f"{pfx}/elements/eeg/eeg[0]", eeg_handler)
    osc_dispatcher.map(f"{pfx}/elements/jaw_clench", eeg_handler)
    osc_dispatcher.map(f"{pfx}/elements/blink", eeg_handler)
    osc_dispatcher.map(f"{pfx}/elements/touching_forehead", eeg_handler)

    try:
        global_osc_server = osc_server.ThreadingOSCUDPServer((ip, port), osc_dispatcher)
        print(f"OSC服务器启动在 {ip}:{port}")
        global_osc_server.serve_forever()
    except Exception as e:
        print(f"OSC服务器错误: {e}")

# 清理函数（终止OSC线程）
def cleanup():
    global global_osc_server, osc_thread
    if global_osc_server:
        global_osc_server.shutdown()
        global_osc_server.server_close()
        global_osc_server = None
    if 'osc_thread' in globals() and osc_thread.is_alive():
        osc_thread.join(1.0)
        osc_thread = None  # 重置线程变量

# ── 通用文本输入（TEXTINPUT 兼容中文输入法）──
def text_input_screen(title, default, validator=None):
    input_text = default
    active = True
    pygame.key.start_text_input()

    while active:
        screen.fill(BLACK)
        prompt = font.render(title, True, WHITE)
        screen.blit(prompt, (50, SCREEN_HEIGHT // 3 - 10))
        box_rect = pygame.Rect(50, SCREEN_HEIGHT // 3 + 30, SCREEN_WIDTH - 100, 40)
        pygame.draw.rect(screen, (60, 60, 60), box_rect)
        pygame.draw.rect(screen, (0, 200, 0), box_rect, 2)
        cursor = "|" if int(time.time() * 2) % 2 == 0 else ""
        surf = font.render(input_text + cursor, True, WHITE)
        screen.blit(surf, (60, SCREEN_HEIGHT // 3 + 38))
        hint = small_font.render("Enter=Confirm  Backspace=Delete  Esc=Use Default", True, GRAY)
        screen.blit(hint, (50, SCREEN_HEIGHT // 3 + 85))
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

# 坦克类
class Tank:
    def __init__(self, x, y, color, is_player=True):
        self.x = x
        self.y = y
        self.color = color
        self.direction = 0  # 0-上, 1-右, 2-下, 3-左
        self.speed = 3 if is_player else 2
        self.is_player = is_player
        self.last_shot = 0
        self.last_turn_time = 0
        self.turn_cooldown = 0.2  # 转向冷却时间
        self.hit_timer = 0  # 被击中闪烁计时器

    def draw(self):
        # 绘制坦克主体
        if self.is_player:
            tank_img = img_tank_head
        else:
            tank_img = img_df_tank

        # 处理被击中闪烁效果
        if self.hit_timer > 0:
            self.hit_timer -= 1
            if self.hit_timer % 4 < 2:  # 每4帧闪烁一次
                return

        # 根据方向旋转坦克图像
        rotated_img = pygame.transform.rotate(tank_img, -self.direction * 90)
        # 获取旋转后的矩形并居中
        rect = rotated_img.get_rect(center=(self.x + TANK_SIZE // 2, self.y + TANK_SIZE // 2))
        screen.blit(rotated_img, rect.topleft)

    def move(self, walls, tanks):
        if self.is_player:
            with eeg_lock:
                left = eeg_commands["left_eyebrow"]
                right = eeg_commands["right_eyebrow"]
                is_forward = (time.time() < eeg_commands["forward_end_time"])

            # 转向控制
            current_time = time.time()
            if left and current_time - self.last_turn_time > self.turn_cooldown:
                self.direction = (self.direction - 1) % 4
                self.last_turn_time = current_time
            if right and current_time - self.last_turn_time > self.turn_cooldown:
                self.direction = (self.direction + 1) % 4
                self.last_turn_time = current_time

            # 前进控制
            if is_forward:
                self._move_forward(walls, tanks)
        else:
            # 敌方坦克AI
            if random.random() < 0.02:  # 随机转向概率
                self.direction = random.randint(0, 3)
            self._move_forward(walls, tanks)

    def _move_forward(self, walls, tanks):
        new_x, new_y = self.x, self.y
        # 根据方向计算新位置
        if self.direction == 0:
            new_y -= self.speed
        elif self.direction == 1:
            new_x += self.speed
        elif self.direction == 2:
            new_y += self.speed
        else:
            new_x -= self.speed

        # 边界检测
        if 0 <= new_x <= SCREEN_WIDTH - TANK_SIZE and 0 <= new_y <= SCREEN_HEIGHT - TANK_SIZE:
            # 碰撞检测
            collision = False
            # 墙壁碰撞
            for wall in walls:
                if (new_x < wall.x + WALL_SIZE and new_x + TANK_SIZE > wall.x and
                        new_y < wall.y + WALL_SIZE and new_y + TANK_SIZE > wall.y):
                    collision = True
                    break
            # 坦克碰撞
            for tank in tanks:
                if tank != self and (new_x < tank.x + TANK_SIZE and new_x + TANK_SIZE > tank.x and
                                     new_y < tank.y + TANK_SIZE and new_y + TANK_SIZE > tank.y):
                    collision = True
                    break
            if not collision:
                self.x, self.y = new_x, new_y

    def shoot(self, bullets):
        current_time = time.time()
        if self.is_player:
            with eeg_lock:
                should_shoot = eeg_commands["blink"]
            # 检查射击冷却
            if should_shoot and current_time - self.last_shot > PLAYER_SHOOT_COOLDOWN:
                cx, cy = self.x + TANK_SIZE // 2, self.y + TANK_SIZE // 2
                bullets.append(Bullet(cx, cy, self.direction, True))
                self.last_shot = current_time
                eeg_commands["blink"] = False  # 重置射击状态
        else:
            # 敌人随机射击
            if random.random() < ENEMY_SHOOT_PROBABILITY:
                cx, cy = self.x + TANK_SIZE // 2, self.y + TANK_SIZE // 2
                bullets.append(Bullet(cx, cy, self.direction, False))

    def get_rect(self):
        """获取坦克的碰撞矩形"""
        return pygame.Rect(self.x, self.y, TANK_SIZE, TANK_SIZE)

    def hit(self):
        """处理被击中的效果"""
        self.hit_timer = 20  # 被击中后闪烁20帧


# 子弹类
class Bullet:
    def __init__(self, x, y, direction, is_player):
        self.x = x - BULLET_SIZE // 2
        self.y = y - BULLET_SIZE // 2
        self.direction = direction
        self.speed = 8 if is_player else 6
        self.is_player = is_player
        self.image = player_bullet_img if is_player else enemy_bullet_img
        self.rect = pygame.Rect(self.x, self.y, BULLET_SIZE, BULLET_SIZE)
        self.lifetime = 60  # 子弹生命周期（帧数）

    def move(self):
        # 根据方向移动
        if self.direction == 0:
            self.y -= self.speed
        elif self.direction == 1:
            self.x += self.speed
        elif self.direction == 2:
            self.y += self.speed
        else:
            self.x -= self.speed

        # 更新矩形位置
        self.rect.topleft = (self.x, self.y)
        self.lifetime -= 1

    def draw(self, screen):
        if self.image:
            # 绘制旋转后的子弹
            rotated_img = pygame.transform.rotate(self.image, -self.direction * 90)
            rect = rotated_img.get_rect(center=self.rect.center)
            screen.blit(rotated_img, rect.topleft)
        else:
            # 图片加载失败时绘制矩形
            color = YELLOW if self.is_player else RED
            pygame.draw.rect(screen, color, self.rect)

    def is_out_of_bounds(self):
        """检测是否超出屏幕边界或生命周期结束"""
        return (self.x < -BULLET_SIZE or
                self.x > SCREEN_WIDTH or
                self.y < -BULLET_SIZE or
                self.y > SCREEN_HEIGHT or
                self.lifetime <= 0)

    def check_collision(self, target_rect):
        """检测与目标的碰撞"""
        return self.rect.colliderect(target_rect)

# 墙壁类
class Wall:
    def __init__(self, x, y, breakable=True):
        self.x = x  # 墙壁x坐标
        self.y = y  # 墙壁y坐标
        self.breakable = breakable  # 是否可破坏（True=可破坏，False=不可破坏）
        self.rect = pygame.Rect(x, y, WALL_SIZE, WALL_SIZE)  # 碰撞检测矩形（核心，不改动）

        # 根据是否可破坏，关联对应的墙壁图片
        if breakable:
            self.image = breakable_wall_img  # 可破坏墙壁图片（如砖墙）
        else:
            self.image = unbreakable_wall_img  # 不可破坏墙壁图片（如钢墙）

    def draw(self):
        # 优先绘制自定义图片
        if self.image:
            # 直接绘制图片（图片尺寸已与WALL_SIZE匹配）
            screen.blit(self.image, (self.x, self.y))
        else:
            # 图片加载失败时，用原始矩形绘制兜底
            color = GRAY if self.breakable else (50, 50, 50)  # 可破坏/不可破坏颜色区分
            pygame.draw.rect(screen, color, self.rect)

            # 为可破坏墙壁添加简单纹理（原有逻辑）
            if self.breakable:
                pygame.draw.rect(
                    screen,
                    (70, 70, 70),  # 深色边框
                    (self.x + 5, self.y + 5, WALL_SIZE - 10, WALL_SIZE - 10),
                    1  # 线宽
                )

    def get_rect(self):
        """返回碰撞检测矩形（供外部调用）"""
        return self.rect
# 爆炸效果类
class Explosion:
    def __init__(self, x, y, size=40):
        self.x = x
        self.y = y
        self.size = size
        self.frame = 0
        self.max_frames = 8  # 爆炸动画帧数

    def draw(self):
        # 绘制简单的爆炸动画
        if self.frame < self.max_frames:
            alpha = 255 - (self.frame * 30)
            color = (255, 200 - self.frame * 20, 0, alpha)
            surf = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (self.size // 2, self.size // 2),
                               self.size // 2 - (self.frame * (self.size // (2 * self.max_frames))))
            screen.blit(surf, (self.x - self.size // 2, self.y - self.size // 2))
            self.frame += 1

    def is_finished(self):
        return self.frame >= self.max_frames


# 显示开始界面
def show_start_screen():
    waiting = True
    while waiting:
        screen.fill(BLACK)

        # 绘制标题
        screen.blit(title_text, (SCREEN_WIDTH // 2 - title_text.get_width() // 2,
                                 SCREEN_HEIGHT // 3))

        # 绘制开始按钮
        pygame.draw.rect(screen, BLUE, start_button)
        screen.blit(start_text, (start_button.centerx - start_text.get_width() // 2,
                                 start_button.centery - start_text.get_height() // 2))

        # 绘制操作说明
        instructions = [
            "Control Instructions:",
            "Blink: Move forward",
            "Clench teeth: Turn ",
            "Touch forehead: Fire ",
            "key_board:spare"
        ]

        for i, text in enumerate(instructions):
            surf = small_font.render(text, True, WHITE)
            screen.blit(surf, (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 100 + i * 30))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cleanup()
                pygame.quit()
                exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if start_button.collidepoint(event.pos):
                    waiting = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    waiting = False


# 主游戏函数
def main():
    # 显示开始界面
    show_start_screen()

    # 初始化游戏元素
    player = Tank(100,
                  SCREEN_HEIGHT // 1.2 - TANK_SIZE // 2, GREEN)

    # 创建墙壁
    walls = []
    # 初始化游戏元素
    player = Tank(100,
                  SCREEN_HEIGHT // 1.2 - TANK_SIZE // 2, GREEN)

    # 替换后的敌人坦克初始化代码（随机位置，避开墙壁）
    enemies = []
    max_attempts = 100  # 最大尝试次数
    for _ in range(3):
        attempts = 0
        while attempts < max_attempts:
            # 随机生成位置（避开外围墙壁）
            x = random.randint(WALL_SIZE, SCREEN_WIDTH - 2 * WALL_SIZE)
            y = random.randint(WALL_SIZE, SCREEN_HEIGHT - 2 * WALL_SIZE)
            # 检查是否与墙壁碰撞
            collide = False
            tank_rect = pygame.Rect(x, y, TANK_SIZE, TANK_SIZE)
            for wall in walls:
                if tank_rect.colliderect(wall.rect):
                    collide = True
                    break
            if not collide:
                enemies.append(Tank(x, y, RED, False))
                break
            attempts += 1
    # 外围不可破坏的墙壁
    for x in range(0, SCREEN_WIDTH, WALL_SIZE):
        walls.append(Wall(x, 0, breakable=False))
        walls.append(Wall(x, SCREEN_HEIGHT - WALL_SIZE, breakable=False))
    for y in range(WALL_SIZE, SCREEN_HEIGHT - WALL_SIZE, WALL_SIZE):
        walls.append(Wall(0, y, breakable=False))
        walls.append(Wall(SCREEN_WIDTH - WALL_SIZE, y, breakable=False))

    # 内部可破坏的墙壁
    for i in range(4, 16):
        for j in range(4, 14):
            if (i % 4 == 0 and j % 2 == 0) and not (i == 10 and j == 7):
                walls.append(Wall(WALL_SIZE * i, WALL_SIZE * j))

    bullets = []
    explosions = []
    score = 0
    clock = pygame.time.Clock()
    running = True

    while running:
        # 绘制背景
        if bg_img:
            screen.blit(bg_img, (0, 0))
        else:
            screen.fill(BLACK)

        # 事件处理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # 空格键备用射击
                    cx, cy = player.x + TANK_SIZE // 2, player.y + TANK_SIZE // 2
                    bullets.append(Bullet(cx, cy, player.direction, True))
                # 方向键备用控制
                elif event.key == pygame.K_LEFT:
                    player.direction = 3
                    player._move_forward(walls, [player] + enemies)
                elif event.key == pygame.K_RIGHT:
                    player.direction = 1
                    player._move_forward(walls, [player] + enemies)
                elif event.key == pygame.K_UP:
                    player.direction = 0
                    player._move_forward(walls, [player] + enemies)
                elif event.key == pygame.K_DOWN:
                    player.direction = 2
                    player._move_forward(walls, [player] + enemies)

        # 更新玩家
        player.move(walls, [player] + enemies)
        player.shoot(bullets)
        player.draw()

        # 更新敌人
        for enemy in enemies[:]:
            enemy.move(walls, [player] + enemies)
            enemy.shoot(bullets)
            enemy.draw()

        # 更新子弹
        for bullet in bullets[:]:
            bullet.move()
            bullet.draw(screen)

            # 边界检测或生命周期结束
            if bullet.is_out_of_bounds():
                bullets.remove(bullet)
                continue

            # 墙壁碰撞
            for wall in walls[:]:
                if wall.breakable and bullet.check_collision(wall.rect):
                    bullets.remove(bullet)
                    # 添加爆炸效果
                    explosions.append(Explosion(wall.x + WALL_SIZE // 2, wall.y + WALL_SIZE // 2))
                    walls.remove(wall)
                    break

            # 坦克碰撞
            if bullet.is_player:
                # 玩家子弹击中敌人
                for enemy in enemies[:]:
                    if bullet.check_collision(enemy.get_rect()):
                        bullets.remove(bullet)
                        enemies.remove(enemy)
                        score += 100
                        # 添加爆炸效果
                        explosions.append(Explosion(enemy.x + TANK_SIZE // 2, enemy.y + TANK_SIZE // 2, 60))
                        # 补充敌人
                        if len(enemies) < ENEMY_MAX_COUNT:
                            max_attempts = 100
                            attempts = 0
                            while attempts < max_attempts:
                                x = random.randint(WALL_SIZE, SCREEN_WIDTH - 2 * WALL_SIZE)
                                y = random.randint(WALL_SIZE, SCREEN_HEIGHT - 2 * WALL_SIZE)
                                # 确保新敌人与玩家保持距离
                                if abs(x - player.x) > 100 and abs(y - player.y) > 100:
                                    enemies.append(Tank(x, y, RED, False))
                                    break
                                attempts += 1
                        break
            else:
                # 敌人子弹击中玩家
                if bullet.check_collision(player.get_rect()):
                    bullets.remove(bullet)
                    player.hit()  # 玩家被击中效果
                    # 玩家生命值逻辑可以在这里添加
                    # 简单处理：直接游戏结束
                    explosions.append(Explosion(player.x + TANK_SIZE // 2, player.y + TANK_SIZE // 2, 80))
                    running = False  # 游戏结束

        # 绘制并更新爆炸效果
        for explosion in explosions[:]:
            explosion.draw()
            if explosion.is_finished():
                explosions.remove(explosion)

        # 绘制墙壁
        for wall in walls:
            wall.draw()

        # 显示分数
        if img_score_bg:
            screen.blit(img_score_bg, (10, 10))
        score_text = font.render(f"score: {score}", True, WHITE)
        screen.blit(score_text, (20, 15))

        # 显示指令状态（调试用）
        with eeg_lock:
            status_texts = [
                f"turn_direction: {eeg_commands['left_eyebrow']}",
                f"turn_direction2: {eeg_commands['right_eyebrow']}",
                f"go: {time.time() < eeg_commands['forward_end_time']}",
                f"blink: {eeg_commands['blink']}"
            ]
        for i, text in enumerate(status_texts):
            surf = small_font.render(text, True, WHITE)
            screen.blit(surf, (20, 60 + i * 25))

        pygame.display.flip()
        clock.tick(FPS)

    # 等待爆炸动画完成
    while explosions:
        screen.fill(BLACK)
        if bg_img:
            screen.blit(bg_img, (0, 0))
        for explosion in explosions[:]:
            explosion.draw()
            if explosion.is_finished():
                explosions.remove(explosion)
        pygame.display.flip()
        clock.tick(FPS)

    # 游戏结束画面
    pygame.draw.rect(screen, BLACK, (SCREEN_WIDTH // 2 - 250, SCREEN_HEIGHT // 2 - 100, 500, 200))
    game_over_text = font.render(f"final score: {score}", True, YELLOW)
    screen.blit(game_over_text, (SCREEN_WIDTH // 2-200, SCREEN_HEIGHT // 2-100))
    pygame.draw.rect(screen, RED, restart_button)
    pygame.draw.rect(screen, RED, quit_button)
    screen.blit(restart_text, (restart_button.centerx - restart_text.get_width() // 2,
                               restart_button.centery - restart_text.get_height() // 2))
    screen.blit(quit_text, (quit_button.centerx - quit_text.get_width() // 2,
                            quit_button.centery - quit_text.get_height() // 2))
    pygame.display.flip()

    # 等待用户选择
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                waiting = False
                cleanup()
                pygame.quit()
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                if restart_button.collidepoint(event.pos):
                    waiting = False
                    cleanup()  # 重启前清理
                    global osc_thread
                    osc_thread = threading.Thread(
                        target=osc_server_thread,
                        args=(OSC_address_prefix, port),
                        daemon=True
                    )
                    osc_thread.start()
                    main()
                elif quit_button.collidepoint(event.pos):
                    waiting = False
                    cleanup()
                    pygame.quit()
                    return

# 启动游戏
if __name__ == "__main__":
    OSC_address_prefix = text_input_screen(
        "Enter OSC prefix (e.g. /hab):", "/hab", validate_prefix)
    port = text_input_screen(
        "Enter OSC port (1024-65535):", str(port), validate_port)
    osc_thread = threading.Thread(target=osc_server_thread,
                                  args=(OSC_address_prefix, port),
                                  daemon=True)
    osc_thread.start()
    main()