import pygame
import random
import time
import math
from pythonosc import dispatcher
from pythonosc import osc_server
from threading import Thread
from collections import deque

# 初始化游戏
pygame.init()
width, height = 700, 700
win = pygame.display.set_mode((width, height))
pygame.display.set_caption("Space Impact Game")

# 加载游戏资源（已添加convert_alpha()处理透明）
bg_img = pygame.image.load("img_space.png").convert()
bg_img = pygame.transform.scale(bg_img, (width, height))
img_player = pygame.image.load("img_spaceship_left.png").convert_alpha()
img_player = pygame.transform.scale(img_player, (60, 40))
img_enemy = pygame.image.load("img_spaceship_right.png").convert_alpha()
img_enemy = pygame.transform.scale(img_enemy, (60, 40))
img_bullet = pygame.image.load("img_beams_seg.png").convert_alpha()
img_bullet = pygame.transform.scale(img_bullet, (30, 10))
img_score_bg = pygame.image.load("img_score.png").convert_alpha()
img_score_bg = pygame.transform.scale(img_score_bg, (150, 50))

# 加载道具图片
img_lasertool = pygame.image.load("img_lasertool.png").convert_alpha()
img_triple_lasertool = pygame.image.load("img_triple_lasertool.png").convert_alpha()
# 缩放道具图片
img_lasertool = pygame.transform.scale(img_lasertool, (40, 40))
img_triple_lasertool = pygame.transform.scale(img_triple_lasertool, (40, 40))

# 游戏变量初始化
player_health = 1000
enemy_health = 1000
font = pygame.font.Font(None, 36)
clock = pygame.time.Clock()
fps = 30

# 玩家设置（固定在左侧，仅上下移动）
player_x = 50
player_y = height // 2
player_speed = 7
player_size = img_player.get_rect().size
player_velocity = 0  # 用于预测位置的速度
player_last_y = player_y  # 上一帧位置

# 跟随型敌人设置
enemy_x = width - 50 - img_enemy.get_width()
enemy_y = height // 2
enemy_size = img_enemy.get_rect().size
# 存储玩家位置和速度历史，每个元素是(位置, 速度, 时间)
player_pos_history = deque(maxlen=int(fps * 4))  # 最多存储4秒的历史数据

# 新增预测型敌人
predicting_enemy_x = width - 150 - img_enemy.get_width()
predicting_enemy_y = height // 2
predicting_enemy_active = False  # 是否激活预测型敌人

# 子弹设置
bullets = []  # [x, y, direction, rect, damage_multiplier]
bullet_speed = 10
bullet_cooldown = 0.5
last_fire_time = 0

# 道具设置
powerups = []  # [x, y, type, rect] type: 'double' 或 'triple'
powerup_speed = bullet_speed // 5  # 子弹速度的五分之一
last_powerup_spawn = 0
powerup_spawn_interval = random.uniform(5, 9)  # 7±2秒

# 武器状态（玩家+敌人）
has_double_shot = False
has_triple_shot = False
double_damage_end = 0  # 玩家双倍伤害结束时间
triple_damage_end = 0  # 玩家三倍伤害结束时间
enemy_has_double_shot = False  # 敌人双子弹状态
enemy_has_triple_shot = False  # 敌人三子弹状态
enemy_double_damage_end = 0  # 敌人双倍伤害结束时间
enemy_triple_damage_end = 0  # 敌人三倍伤害结束时间

# 游戏状态
game_over = False

# OSC设置
ip = "127.0.0.1"
OSC_address_prefix = ""
port_number = None
acc_data = {"x": 0, "y": 0}
jaw_clench = 0

# 按钮设置
restart_button = pygame.Rect(width//2 - 100, height//2 - 50, 200, 50)
quit_button = pygame.Rect(width//2 - 100, height//2 + 20, 200, 50)
restart_text = font.render("Restart", True, (255,255,255))
quit_text = font.render("Quit", True, (255,255,255))


# ------------------------------
# 核心游戏逻辑函数
# ------------------------------
def reset_game():
    """重置游戏状态（包含敌人道具状态）"""
    global player_y, enemy_y, predicting_enemy_y, predicting_enemy_active
    global bullets, powerups, player_health, enemy_health
    global game_over, last_fire_time, player_pos_history, last_powerup_spawn
    global has_double_shot, has_triple_shot, double_damage_end, triple_damage_end
    global enemy_has_double_shot, enemy_has_triple_shot, enemy_double_damage_end, enemy_triple_damage_end
    global player_last_y, player_velocity
    
    player_y = height // 2
    player_last_y = player_y
    player_velocity = 0
    enemy_y = height // 2
    predicting_enemy_y = height // 2
    predicting_enemy_active = True
    bullets = []
    powerups = []
    player_health = 1000
    enemy_health = 1000
    game_over = False
    last_fire_time = 0
    last_powerup_spawn = time.time()
    player_pos_history.clear()
    # 重置玩家武器状态
    has_double_shot = False
    has_triple_shot = False
    double_damage_end = 0
    triple_damage_end = 0
    # 重置敌人武器状态
    enemy_has_double_shot = False
    enemy_has_triple_shot = False
    enemy_double_damage_end = 0
    enemy_triple_damage_end = 0


def fire_bullet(x, y, direction, is_player=True):
    """生成子弹，支持玩家和敌人的多子弹、角度发射及伤害加成"""
    base_damage = 10
    damage_multiplier = 1
    current_time = time.time()
    
    # 区分玩家/敌人的伤害加成
    if is_player:
        if current_time < double_damage_end:
            damage_multiplier = 2
        if current_time < triple_damage_end:
            damage_multiplier = 3
    else:
        if current_time < enemy_double_damage_end:
            damage_multiplier = 2
        if current_time < enemy_triple_damage_end:
            damage_multiplier = 3
    
    # 区分玩家/敌人的多子弹发射逻辑
    if (is_player and has_triple_shot) or (not is_player and enemy_has_triple_shot):
        # 三子弹（5度夹角）
        angles = [-5, 0, 5]
        for angle in angles:
            rad = math.radians(angle)
            bullet_rect = img_bullet.get_rect(center=(x, y))
            vel_x = bullet_speed * direction * math.cos(rad)
            vel_y = bullet_speed * direction * math.sin(rad)
            bullets.append([bullet_rect.x, bullet_rect.y, vel_x, vel_y, bullet_rect, damage_multiplier, is_player])
    elif (is_player and has_double_shot) or (not is_player and enemy_has_double_shot):
        # 双子弹（1度夹角）
        angles = [-1, 1]
        for angle in angles:
            rad = math.radians(angle)
            bullet_rect = img_bullet.get_rect(center=(x, y))
            vel_x = bullet_speed * direction * math.cos(rad)
            vel_y = bullet_speed * direction * math.sin(rad)
            bullets.append([bullet_rect.x, bullet_rect.y, vel_x, vel_y, bullet_rect, damage_multiplier, is_player])
    else:
        # 普通子弹
        bullet_rect = img_bullet.get_rect(center=(x, y))
        bullets.append([bullet_rect.x, bullet_rect.y, bullet_speed * direction, 0, bullet_rect, damage_multiplier, is_player])


def spawn_powerup():
    """随机生成道具（逻辑不变）"""
    global last_powerup_spawn, powerup_spawn_interval
    current_time = time.time()
    
    if current_time - last_powerup_spawn > powerup_spawn_interval:
        # 从中间向两边发送
        spawn_x = width // 2
        spawn_y = random.randint(50, height - 50)
        
        # 决定方向（左或右）
        direction = random.choice([-1, 1])
        
        # 决定道具类型：只有获得双子弹后才出现三子弹
        if has_double_shot and random.random() < 0.5:
            powerup_type = 'triple'
            powerup_img = img_triple_lasertool
        else:
            powerup_type = 'double'
            powerup_img = img_lasertool
            
        powerup_rect = powerup_img.get_rect(center=(spawn_x, spawn_y))
        powerups.append([spawn_x, spawn_y, direction, powerup_type, powerup_rect])
        
        # 重置计时器和间隔
        last_powerup_spawn = current_time
        powerup_spawn_interval = random.uniform(5, 9)


def update_enemy_pos():
    """更新普通敌人位置为玩家4秒前的位置（逻辑不变）"""
    global enemy_y
    if len(player_pos_history) >= fps * 4:
        enemy_y = player_pos_history[0][0]  # 只取位置信息
    enemy_y = max(enemy_size[1]//2, min(enemy_y, height - enemy_size[1]//2))


def update_predicting_enemy_pos():
    """更新预测型敌人位置，使用玩家当前位置和2秒前的速度预测玩家2秒后位置"""
    global predicting_enemy_y, predicting_enemy_active
    
    if predicting_enemy_active and len(player_pos_history) >= fps * 2:
        # 获取玩家当前位置（假设最新位置在history末尾，或有单独变量存储）
        current_pos = player_y  # 假设player_pos是玩家当前位置
        # 获取2秒前的速度（过时速度数据）
        past_vel = player_pos_history[0][1]  # 仅取2秒前的速度
        
        # 预测玩家2秒后的位置：当前位置 + 2秒前的速度 * 2秒（预测未来2秒）
        # （注：用当前位置作为起点，结合过时速度推测未来，更符合“已知现在位置”的前提）
        predicted_future_y = current_pos + past_vel * 2  # 关键：预测未来2秒的位移
        
        # 平滑移动到预测的未来位置
        move_speed = 7
        if predicted_future_y > predicting_enemy_y:
            predicting_enemy_y += min(move_speed, predicted_future_y - predicting_enemy_y)
        elif predicted_future_y < predicting_enemy_y:
            predicting_enemy_y -= min(move_speed, predicting_enemy_y - predicted_future_y)
            
        # 限制在屏幕内
        predicting_enemy_y = max(enemy_size[1]//2, min(predicting_enemy_y, height - enemy_size[1]//2))

def check_collision():
    """检测所有碰撞（新增敌人道具碰撞逻辑）"""
    global player_health, enemy_health, game_over
    global has_double_shot, has_triple_shot, double_damage_end, triple_damage_end
    global enemy_has_double_shot, enemy_has_triple_shot, enemy_double_damage_end, enemy_triple_damage_end
    
    player_rect = img_player.get_rect(center=(player_x + player_size[0]//2, player_y))
    enemy_rect = img_enemy.get_rect(center=(enemy_x + enemy_size[0]//2, enemy_y))
    predicting_enemy_rect = img_enemy.get_rect(center=(predicting_enemy_x + enemy_size[0]//2, predicting_enemy_y))
    
    # 检测子弹碰撞
    for bullet in bullets[:]:
        bullet_x, bullet_y, vel_x, vel_y, bullet_rect, damage, is_player = bullet
        
        # 子弹出界检测
        if bullet_x < 0 or bullet_x > width or bullet_y < 0 or bullet_y > height:
            bullets.remove(bullet)
            continue
        
        # 玩家子弹击中敌人
        if is_player:
            if enemy_rect.colliderect(bullet_rect):
                bullets.remove(bullet)
                enemy_health -= damage
                if enemy_health <= 0:
                    enemy_health = 1000  # 敌人复活
            if predicting_enemy_active and predicting_enemy_rect.colliderect(bullet_rect):
                bullets.remove(bullet)
                enemy_health -= damage
                if enemy_health <= 0:
                    enemy_health = 1000  # 敌人复活
        # 敌人子弹击中玩家
        else:
            if player_rect.colliderect(bullet_rect):
                bullets.remove(bullet)
                player_health -= 10  # 基准扣除10血量
                if player_health <= 0:
                    game_over = True
    
    # 检测道具碰撞
    current_time = time.time()
    for powerup in powerups[:]:
        p_x, p_y, p_dir, p_type, p_rect = powerup
        
        # 玩家捡到道具
        if player_rect.colliderect(p_rect):
            powerups.remove(powerup)
            if p_type == 'double':
                if has_triple_shot:
                    double_damage_end = current_time + 20
                else:
                    has_double_shot = True
            elif p_type == 'triple':
                if not has_triple_shot:
                    has_triple_shot = True
                else:
                    triple_damage_end = current_time + 20
        
        # 敌人捡到道具
        if enemy_rect.colliderect(p_rect) or (predicting_enemy_active and predicting_enemy_rect.colliderect(p_rect)):
            powerups.remove(powerup)
            if p_type == 'double':
                if enemy_has_triple_shot:
                    enemy_double_damage_end = current_time + 20
                else:
                    enemy_has_double_shot = True
            elif p_type == 'triple':
                if not enemy_has_triple_shot:
                    enemy_has_triple_shot = True
                else:
                    enemy_triple_damage_end = current_time + 20


# ------------------------------
# OSC相关函数
# ------------------------------
def acc_handler(address, *args):
    global acc_data
    if len(args) >= 2:
        acc_data["y"] = args[0]


def jaw_clench_handler(address, *args):
    global jaw_clench
    if len(args) >= 1:
        jaw_clench = args[0]


def osc_server_thread():
    if not port_number:
        return
    osc_dispatcher = dispatcher.Dispatcher()
    osc_dispatcher.map(f"{OSC_address_prefix}/acc", acc_handler)
    osc_dispatcher.map(f"{OSC_address_prefix}/elements/jaw_clench", jaw_clench_handler)
    server = osc_server.ThreadingOSCUDPServer((ip, port_number), osc_dispatcher)
    server.serve_forever()


def get_osc_input(prompt):
    input_text = ""
    active = True
    while active:
        win.fill((0,0,0))
        prompt_surface = font.render(prompt, True, (255,255,255))
        win.blit(prompt_surface, (50, height//3))
        input_surface = font.render(input_text, True, (255,255,255))
        win.blit(input_surface, (50, height//3 + 40))
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    active = False
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    input_text += event.unicode
    return input_text


# ------------------------------
# 界面绘制函数
# ------------------------------
def draw_game():
    """绘制游戏主界面"""
    # 绘制背景
    win.blit(bg_img, (0, 0))

    # 绘制玩家和敌人
    player_rect = img_player.get_rect(center=(player_x + player_size[0]//2, player_y))
    win.blit(img_player, player_rect)
    
    enemy_rect = img_enemy.get_rect(center=(enemy_x + enemy_size[0]//2, enemy_y))
    win.blit(img_enemy, enemy_rect)
    
    # 绘制预测型敌人
    if predicting_enemy_active:
        pred_enemy_rect = img_enemy.get_rect(center=(predicting_enemy_x + enemy_size[0]//2, predicting_enemy_y))
        win.blit(img_enemy, pred_enemy_rect)

    # 绘制子弹
    for bullet in bullets:
        bullet_x, bullet_y, vel_x, vel_y, bullet_rect, _, is_player = bullet
        angle = math.degrees(math.atan2(vel_y, vel_x))
        rotated_bullet = pygame.transform.rotate(img_bullet, -angle)
        win.blit(rotated_bullet, (bullet_x, bullet_y))

    # 绘制道具
    for powerup in powerups:
        p_x, p_y, _, p_type, p_rect = powerup
        if p_type == 'double':
            win.blit(img_lasertool, (p_x, p_y))
        else:
            win.blit(img_triple_lasertool, (p_x, p_y))

    # 绘制血量
    win.blit(img_score_bg, (10, 10))
    health_surface = font.render(f"Health: {player_health}", True, (255,255,255))
    win.blit(health_surface, (60, 20))
    
    # 绘制敌人血量
    win.blit(img_score_bg, (width - 160, 10))
    enemy_health_surface = font.render(f"Enemy: {enemy_health}", True, (255,255,255))
    win.blit(enemy_health_surface, (width - 110, 20))
    
    # 绘制玩家武器状态和伤害加成
    current_time = time.time()
    if has_double_shot and not has_triple_shot:
        status_surface = font.render("Double Shot Active", True, (0,255,0))
        win.blit(status_surface, (10, height - 40))
    elif has_triple_shot:
        status_surface = font.render("Triple Shot Active", True, (0,255,255))
        win.blit(status_surface, (10, height - 40))
    
    if current_time < double_damage_end:
        time_left = int(double_damage_end - current_time)
        dmg_surface = font.render(f"Double Damage: {time_left}s", True, (255,255,0))
        win.blit(dmg_surface, (width - 200, height - 60))
    elif current_time < triple_damage_end:
        time_left = int(triple_damage_end - current_time)
        dmg_surface = font.render(f"Triple Damage: {time_left}s", True, (255,165,0))
        win.blit(dmg_surface, (width - 200, height - 60))

    # 绘制敌人武器状态和伤害加成
    if enemy_has_double_shot and not enemy_has_triple_shot:
        enemy_status = font.render("Enemy: Double Shot", True, (255,0,0))
        win.blit(enemy_status, (width - 220, 70))
    elif enemy_has_triple_shot:
        enemy_status = font.render("Enemy: Triple Shot", True, (255,0,255))
        win.blit(enemy_status, (width - 220, 70))
    
    if current_time < enemy_double_damage_end:
        enemy_time = int(enemy_double_damage_end - current_time)
        enemy_dmg = font.render(f"Enemy Double Dmg: {enemy_time}s", True, (255,0,0))
        win.blit(enemy_dmg, (width - 250, 100))
    elif current_time < enemy_triple_damage_end:
        enemy_time = int(enemy_triple_damage_end - current_time)
        enemy_dmg = font.render(f"Enemy Triple Dmg: {enemy_time}s", True, (255,0,0))
        win.blit(enemy_dmg, (width - 250, 100))

    pygame.display.update()


def draw_game_over():
    """绘制游戏结束界面"""
    overlay = pygame.Surface((width, height))
    overlay.set_alpha(128)
    overlay.fill((0,0,0))
    win.blit(overlay, (0,0))

    game_over_surface = font.render("Game Over", True, (255,0,0))
    win.blit(game_over_surface, (width//2 - game_over_surface.get_width()//2, height//2 - 100))

    pygame.draw.rect(win, (255,0,0), restart_button)
    pygame.draw.rect(win, (0,0,0), quit_button)
    win.blit(restart_text, (restart_button.centerx - restart_text.get_width()//2, restart_button.centery - restart_text.get_height()//2))
    win.blit(quit_text, (quit_button.centerx - quit_text.get_width()//2, quit_button.centery - quit_text.get_height()//2))

    pygame.display.update()


# ------------------------------
# 游戏主循环
# ------------------------------
def game_loop():
    global OSC_address_prefix, port_number, player_y, last_fire_time, jaw_clench
    global player_velocity, player_last_y

    # 获取OSC配置
    OSC_address_prefix = get_osc_input("Please enter OSC address prefix:")
    port_str = get_osc_input("Please enter port number:")
    port_number = int(port_str) if port_str.isdigit() else 5005

    # 启动OSC线程
    osc_thread = Thread(target=osc_server_thread, daemon=True)
    osc_thread.start()

    # 重置游戏
    reset_game()

    while True:
        current_time = time.time()

        # 事件处理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if not game_over and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and current_time - last_fire_time > bullet_cooldown:
                    # 玩家开火
                    fire_bullet(player_x + player_size[0], player_y, 1, True)
                    # 敌人开火
                    fire_bullet(enemy_x, enemy_y, -1, False)
                    if predicting_enemy_active:
                        fire_bullet(predicting_enemy_x, predicting_enemy_y, -1, False)
                    last_fire_time = current_time
            if game_over and event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if restart_button.collidepoint(mx, my):
                    reset_game()
                elif quit_button.collidepoint(mx, my):
                    pygame.quit()
                    exit()

        # 游戏运行中逻辑
        if not game_over:
            # 1. 玩家移动控制
            # 计算玩家速度（用于预测）
            player_velocity = player_y - player_last_y
            player_last_y = player_y
            
            # OSC加速度控制
            if acc_data["y"] < -0.5:
                player_y -= player_speed
            elif acc_data["y"] > 0.5:
                player_y += player_speed
            # 键盘控制
            keys = pygame.key.get_pressed()
            if keys[pygame.K_UP]:
                player_y -= player_speed
            if keys[pygame.K_DOWN]:
                player_y += player_speed
            # 限制玩家在屏幕内
            player_y = max(player_size[1]//2, min(player_y, height - player_size[1]//2))

            # 2. 记录玩家位置和速度历史（位置, 速度, 时间）
            player_pos_history.append((player_y, player_velocity, current_time))

            # 3. OSC咬牙开火
            if jaw_clench == 1 and current_time - last_fire_time > bullet_cooldown:
                fire_bullet(player_x + player_size[0], player_y, 1, True)
                fire_bullet(enemy_x, enemy_y, -1, False)
                if predicting_enemy_active:
                    fire_bullet(predicting_enemy_x, predicting_enemy_y, -1, False)
                last_fire_time = current_time
                jaw_clench = 0

            # 4. 更新敌人位置
            update_enemy_pos()
            update_predicting_enemy_pos()

            # 5. 生成道具
            spawn_powerup()

            # 6. 更新子弹位置
            for bullet in bullets:
                bullet[0] += bullet[2]  # x += x方向速度
                bullet[1] += bullet[3]  # y += y方向速度
                bullet[4].x = bullet[0]
                bullet[4].y = bullet[1]

            # 7. 更新道具位置
            for powerup in powerups:
                powerup[0] += powerup_speed * powerup[2]  # x += 速度 * 方向
                powerup[4].x = powerup[0]
                # 移除出界道具
                if powerup[0] < 0 or powerup[0] > width:
                    powerups.remove(powerup)

            # 8. 碰撞检测
            check_collision()

            # 9. 绘制游戏界面
            draw_game()

        # 游戏结束逻辑
        else:
            draw_game_over()

        # 控制帧率
        clock.tick(fps)


if __name__ == "__main__":
    game_loop()