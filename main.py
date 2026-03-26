import math
import json
import os
import struct
import tempfile
import wave
from dataclasses import dataclass

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.properties import StringProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget


Window.clearcolor = (0.74, 0.87, 1.0, 1.0)
Window.size = (480, 800)


@dataclass
class BottleData:
    x: float
    y: float
    width: float
    height: float
    moving: bool = False
    move_range: float = 0.0
    move_speed: float = 0.0
    phase: float = 0.0
    base_x: float = 0.0

    def __post_init__(self):
        self.base_x = self.x


@dataclass
class BulletData:
    x: float
    y: float
    vx: float
    vy: float
    radius: float = 9.0
    life: float = 2.0


@dataclass
class ObstacleData:
    x: float
    y: float
    width: float
    height: float
    moving: bool = False
    move_range: float = 0.0
    move_speed: float = 0.0
    phase: float = 0.0
    base_y: float = 0.0

    def __post_init__(self):
        self.base_y = self.y


@dataclass
class ParticleData:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float
    r: float
    g: float
    b: float


class SoundBank:
    def __init__(self):
        self.sounds = {}
        self.enabled = True
        self.base_dir = os.path.join(tempfile.gettempdir(), "bottle_shooter_audio")
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            self.sounds["shoot"] = self._build_sound("shoot.wav", [(710, 0.05), (540, 0.03)], 0.25)
            self.sounds["hit"] = self._build_sound("hit.wav", [(880, 0.04), (1120, 0.04)], 0.28)
            self.sounds["clear"] = self._build_sound("clear.wav", [(660, 0.06), (820, 0.06), (980, 0.08)], 0.24)
            self.sounds["fail"] = self._build_sound("fail.wav", [(320, 0.08), (240, 0.1)], 0.24)
            self.sounds["menu"] = self._build_sound("menu.wav", [(520, 0.05), (780, 0.08)], 0.22)
        except OSError:
            self.enabled = False

    def _build_sound(self, filename, notes, volume):
        path = os.path.join(self.base_dir, filename)
        if not os.path.exists(path):
            self._write_wave(path, notes, volume)
        sound = SoundLoader.load(path)
        if sound is not None:
            sound.volume = 0.45
        return sound

    def _write_wave(self, path, notes, volume):
        sample_rate = 22050
        frames = []
        fade_samples = max(1, int(sample_rate * 0.008))
        for frequency, duration in notes:
            count = max(1, int(sample_rate * duration))
            for index in range(count):
                env = 1.0
                if index < fade_samples:
                    env = index / fade_samples
                elif count - index < fade_samples:
                    env = (count - index) / fade_samples
                value = math.sin(2 * math.pi * frequency * (index / sample_rate))
                sample = int(32767 * volume * env * value)
                frames.append(struct.pack("<h", sample))
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(frames))

    def play(self, name):
        sound = self.sounds.get(name)
        if not self.enabled or sound is None:
            return
        sound.stop()
        sound.play()


class GameWidget(Widget):
    hud_text = StringProperty("")
    status_text = StringProperty("")
    center_text = StringProperty("")
    summary_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.level = 1
        self.score = 0
        self.high_score = 0
        self.best_level_reached = 1
        self.shots_left = 0
        self.shots_fired = 0
        self.hits_this_level = 0
        self.level_target_count = 0
        self.streak = 0
        self.best_streak = 0
        self.level_complete = False
        self.game_finished = False
        self.game_started = False
        self.paused = False
        self.aiming_touch = None
        self.bottles = []
        self.bullets = []
        self.obstacles = []
        self.particles = []
        self.crosshair = (0, 0)
        self.gun_angle = 0.0
        self.fire_cooldown = 0.0
        self.next_level_event = None
        self.sound_bank = SoundBank()
        self.save_path = self._resolve_save_path()
        self._load_progress()
        self.bind(size=self._refresh_layout, pos=self._refresh_layout)
        Clock.schedule_interval(self.update, 1 / 60)
        self._refresh_layout()

    def _refresh_layout(self, *_args):
        self.ground_y = self.height * 0.12
        self.platform_x = self.width * 0.74
        self.platform_y = self.height * 0.34
        self.platform_width = self.width * 0.22
        self.gun_x = self.width * 0.14
        self.gun_y = self.height * 0.24
        self.crosshair = (self.width * 0.55, self.height * 0.48)
        self.load_level(self.level, keep_score=True, preserve_flow=True)

    def _resolve_save_path(self):
        app = App.get_running_app()
        base_dir = getattr(app, "user_data_dir", None) or os.getcwd()
        try:
            os.makedirs(base_dir, exist_ok=True)
        except OSError:
            base_dir = os.getcwd()
        return os.path.join(base_dir, "bottle_shooter_save.json")

    def _load_progress(self):
        try:
            with open(self.save_path, "r", encoding="utf-8") as save_file:
                data = json.load(save_file)
        except (OSError, json.JSONDecodeError):
            data = {}
        self.high_score = int(data.get("high_score", 0))
        self.best_level_reached = max(1, int(data.get("best_level_reached", 1)))
        self._update_summary()

    def _save_progress(self):
        data = {
            "high_score": self.high_score,
            "best_level_reached": self.best_level_reached,
        }
        try:
            with open(self.save_path, "w", encoding="utf-8") as save_file:
                json.dump(data, save_file)
        except OSError:
            pass

    def _register_progress(self):
        updated = False
        if self.score > self.high_score:
            self.high_score = self.score
            updated = True
        if self.level > self.best_level_reached:
            self.best_level_reached = self.level
            updated = True
        if updated:
            self._save_progress()
        self._update_summary()

    def _update_summary(self, message=None):
        base = (
            f"High Score: {self.high_score}\n"
            f"Best Level: {self.best_level_reached}\n"
            f"Best Streak: {self.best_streak}"
        )
        self.summary_text = f"{message}\n{base}" if message else base

    def load_level(self, level, keep_score=False, preserve_flow=False):
        self.level = max(1, min(50, level))
        self.level_complete = False
        if not preserve_flow:
            self.game_finished = False
        self.center_text = ""
        self.summary_text = ""
        if not keep_score and self.level == 1:
            self.score = 0
            self.best_streak = 0

        self._cancel_next_level()

        self.bottles = []
        self.bullets = []
        self.obstacles = []
        self.particles = []
        self.shots_fired = 0
        self.hits_this_level = 0
        self.streak = 0

        difficulty = self.level - 1
        rows = min(3 + difficulty // 10, 6)
        cols = min(3 + difficulty // 7, 7)
        spacing_x = self.width * 0.06
        spacing_y = self.height * 0.055
        bottle_w = self.width * 0.045
        bottle_h = self.height * 0.07
        base_y = self.platform_y + self.height * 0.03

        for row in range(rows):
            row_cols = max(2, cols - row + (difficulty % 2))
            row_width = (row_cols - 1) * spacing_x
            for col in range(row_cols):
                x = self.platform_x - row_width / 2 + col * spacing_x
                y = base_y + row * spacing_y
                moving = difficulty >= 8 and (row + col + self.level) % 3 == 0
                self.bottles.append(
                    BottleData(
                        x=x,
                        y=y,
                        width=bottle_w,
                        height=bottle_h,
                        moving=moving,
                        move_range=self.width * min(0.02 + difficulty * 0.0008, 0.055),
                        move_speed=min(1.3 + difficulty * 0.05, 4.0),
                        phase=(row * 0.7 + col * 0.3 + self.level * 0.4),
                    )
                )
        self.level_target_count = len(self.bottles)

        if difficulty >= 5:
            obstacle_count = min(1 + difficulty // 12, 3)
            for index in range(obstacle_count):
                self.obstacles.append(
                    ObstacleData(
                        x=self.width * (0.44 + index * 0.12),
                        y=self.height * (0.22 + (index % 2) * 0.12),
                        width=self.width * 0.025,
                        height=self.height * (0.19 + index * 0.04),
                        moving=difficulty >= 16 and index % 2 == 0,
                        move_range=self.height * min(0.025 + difficulty * 0.001, 0.07),
                        move_speed=min(0.9 + difficulty * 0.04, 2.8),
                        phase=index * 0.8 + self.level * 0.35,
                    )
                )

        self.shots_left = max(3, 7 - difficulty // 8)
        if self.level >= 35:
            self.shots_left = max(2, self.shots_left - 1)

        if self.game_started:
            self.status_text = "Drag karke aim karo, chhorte hi fire hoga"
        else:
            self.status_text = "Play dabao aur bottles girao"
        self._update_hud()
        self.redraw()

    def _update_hud(self):
        self.hud_text = (
            f"Level: {self.level}/50    "
            f"Score: {self.score}    "
            f"High: {self.high_score}    "
            f"Bullets: {self.shots_left}    "
            f"Streak: {self.streak}"
        )

    def _cancel_next_level(self):
        if self.next_level_event is not None:
            self.next_level_event.cancel()
            self.next_level_event = None

    def restart_game(self):
        self._cancel_next_level()
        self.game_started = True
        self.paused = False
        self.score = 0
        self.best_streak = 0
        self.load_level(1)
        self.status_text = "Naya game shuru"
        self.sound_bank.play("menu")

    def reload_level(self):
        self._cancel_next_level()
        self.load_level(self.level, keep_score=True)
        self.status_text = "Phir se try karo"

    def advance_level(self, *_args):
        self.next_level_event = None
        if self.level < 50:
            self.load_level(self.level + 1, keep_score=True)
            self.status_text = "Difficulty badh gayi hai"
        else:
            self.game_finished = True
            self.center_text = "50 levels clear!"
            self.status_text = "Restart dabao aur high score beat karo"
            self._register_progress()
            self._update_summary(f"Final Score: {self.score}")
            self._update_hud()

    def start_game(self):
        self.game_started = True
        self.paused = False
        self.score = 0
        self.best_streak = 0
        self.load_level(1)
        self.status_text = "Game shuru. Drag and release!"
        self.sound_bank.play("menu")

    def toggle_pause(self):
        if not self.game_started or self.game_finished:
            return
        self.paused = not self.paused
        if self.paused:
            self.status_text = "Paused hai. Resume dabao"
            self.center_text = "Paused"
        else:
            self.center_text = ""
            self.status_text = "Resume ho gaya. Aim karo"
        self.redraw()

    def on_touch_down(self, touch):
        if not self.game_started:
            return super().on_touch_down(touch)
        if touch.y < self.height * 0.16:
            return super().on_touch_down(touch)
        if self.paused or self.level_complete or self.game_finished:
            return True
        self.aiming_touch = touch.uid
        self.crosshair = (touch.x, touch.y)
        self._update_gun_angle()
        self.redraw()
        return True

    def on_touch_move(self, touch):
        if touch.uid != self.aiming_touch:
            return super().on_touch_move(touch)
        self.crosshair = (touch.x, touch.y)
        self._update_gun_angle()
        self.redraw()
        return True

    def on_touch_up(self, touch):
        if touch.uid != self.aiming_touch:
            return super().on_touch_up(touch)
        self.aiming_touch = None
        self.crosshair = (touch.x, touch.y)
        self._update_gun_angle()
        self.shoot()
        self.redraw()
        return True

    def _update_gun_angle(self):
        dx = self.crosshair[0] - self.gun_x
        dy = self.crosshair[1] - self.gun_y
        self.gun_angle = math.atan2(dy, max(dx, 1))

    def _spawn_particles(self, x, y, colors, count, speed_scale):
        for index in range(count):
            angle = (math.pi * 2 * index) / max(1, count) + (self.level * 0.12)
            speed = speed_scale * (0.7 + (index % 3) * 0.18)
            self.particles.append(
                ParticleData(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed + self.height * 0.03,
                    size=self.width * 0.012,
                    life=0.38 + (index % 4) * 0.04,
                    r=colors[0],
                    g=colors[1],
                    b=colors[2],
                )
            )

    def shoot(self):
        if self.level_complete or self.game_finished or self.shots_left <= 0 or self.fire_cooldown > 0:
            return

        dx = self.crosshair[0] - self.gun_x
        dy = self.crosshair[1] - self.gun_y
        distance = math.hypot(dx, dy)
        if distance < 1:
            return

        speed = self.width * 1.8
        self.bullets.append(
            BulletData(
                x=self.gun_x + math.cos(self.gun_angle) * self.width * 0.1,
                y=self.gun_y + math.sin(self.gun_angle) * self.width * 0.1,
                vx=dx / distance * speed,
                vy=dy / distance * speed,
            )
        )
        self.shots_left -= 1
        self.shots_fired += 1
        self.fire_cooldown = 0.18
        self.status_text = "Nice shot!" if self.streak >= 2 else "Aim set, fire ho gaya"
        self.sound_bank.play("shoot")
        self._update_hud()

    def update(self, dt):
        if not self.game_started:
            self.center_text = "Bottle Shooter"
            self.redraw()
            return

        if self.paused:
            self.redraw()
            return

        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)

        for bottle in self.bottles:
            if bottle.moving:
                bottle.x = bottle.base_x + math.sin(Clock.get_boottime() * bottle.move_speed + bottle.phase) * bottle.move_range

        for obstacle in self.obstacles:
            if obstacle.moving:
                obstacle.y = obstacle.base_y + math.sin(Clock.get_boottime() * obstacle.move_speed + obstacle.phase) * obstacle.move_range

        remaining_particles = []
        for particle in self.particles:
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vy -= self.height * 0.18 * dt
            particle.life -= dt
            particle.size *= 0.985
            if particle.life > 0:
                remaining_particles.append(particle)
        self.particles = remaining_particles

        remaining_bullets = []
        for bullet in self.bullets:
            bullet.x += bullet.vx * dt
            bullet.y += bullet.vy * dt
            bullet.life -= dt

            if bullet.life <= 0 or bullet.x > self.width + 30 or bullet.y > self.height + 30 or bullet.y < -30:
                continue

            if self._bullet_hits_obstacle(bullet):
                self.streak = 0
                self.status_text = "Obstacle par lag gayi"
                self._spawn_particles(bullet.x, bullet.y, (0.75, 0.4, 0.2), 8, self.width * 0.12)
                self._update_hud()
                continue

            hit_bottle = self._get_hit_bottle(bullet)
            if hit_bottle is not None:
                self.bottles.remove(hit_bottle)
                self.hits_this_level += 1
                self.streak += 1
                self.best_streak = max(self.best_streak, self.streak)
                hit_bonus = min((self.streak - 1) * 2, 12)
                self.score += 10 + hit_bonus
                self._register_progress()
                self._update_hud()
                self._spawn_particles(
                    hit_bottle.x + hit_bottle.width / 2,
                    hit_bottle.y + hit_bottle.height / 2,
                    (0.24, 0.86, 0.7),
                    12,
                    self.width * 0.18,
                )
                self.sound_bank.play("hit")
                if self.streak >= 3:
                    self.status_text = f"Streak x{self.streak}! Bonus mila"
                else:
                    self.status_text = "Bottle hit!"
                if not self.bottles:
                    self.level_complete = True
                    accuracy = self.hits_this_level / max(self.shots_fired, 1)
                    clear_bonus = self.shots_left * 5 + int(accuracy * 20)
                    self.score += clear_bonus
                    self._register_progress()
                    self._update_hud()
                    self.center_text = f"Level {self.level} clear! +{clear_bonus}"
                    self.status_text = "Agla level aa raha hai..."
                    self._spawn_particles(self.width * 0.5, self.height * 0.6, (1.0, 0.82, 0.2), 20, self.width * 0.16)
                    self.sound_bank.play("clear")
                    self.next_level_event = Clock.schedule_once(self.advance_level, 1.0)
                continue

            remaining_bullets.append(bullet)

        self.bullets = remaining_bullets

        if self.shots_left <= 0 and self.bullets == [] and self.bottles and not self.level_complete:
            if self.center_text != "Level fail":
                self.streak = 0
                self.center_text = "Level fail"
                self.status_text = f"{len(self.bottles)} bottles baki hain. Reload dabao"
                self._register_progress()
                self._update_summary(f"Run Over: {self.score} score, Level {self.level}")
                self.sound_bank.play("fail")
                self._spawn_particles(self.width * 0.5, self.height * 0.48, (0.92, 0.28, 0.24), 14, self.width * 0.11)
                self._update_hud()

        self.redraw()

    def _bullet_hits_obstacle(self, bullet):
        for obstacle in self.obstacles:
            if (
                obstacle.x <= bullet.x <= obstacle.x + obstacle.width
                and obstacle.y <= bullet.y <= obstacle.y + obstacle.height
            ):
                return True
        return False

    def _get_hit_bottle(self, bullet):
        for bottle in self.bottles:
            if (
                bottle.x <= bullet.x <= bottle.x + bottle.width
                and bottle.y <= bullet.y <= bottle.y + bottle.height
            ):
                return bottle
        return None

    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.75, 0.88, 1.0)
            Rectangle(pos=self.pos, size=self.size)

            Color(1, 1, 1, 0.25)
            Ellipse(pos=(self.width * 0.08, self.height * 0.78), size=(self.width * 0.28, self.height * 0.12))
            Ellipse(pos=(self.width * 0.46, self.height * 0.84), size=(self.width * 0.22, self.height * 0.09))

            Color(0.63, 0.86, 0.44)
            Ellipse(pos=(-self.width * 0.05, self.ground_y - self.height * 0.03), size=(self.width * 0.48, self.height * 0.14))
            Ellipse(pos=(self.width * 0.2, self.ground_y - self.height * 0.02), size=(self.width * 0.4, self.height * 0.16))
            Ellipse(pos=(self.width * 0.52, self.ground_y - self.height * 0.025), size=(self.width * 0.42, self.height * 0.15))

            Color(0.47, 0.29, 0.16)
            Rectangle(pos=(0, self.ground_y - self.height * 0.025), size=(self.width, self.height * 0.05))
            Rectangle(pos=(self.platform_x - self.platform_width / 2, self.platform_y), size=(self.platform_width, self.height * 0.015))

            for obstacle in self.obstacles:
                if obstacle.moving:
                    Color(0.72, 0.38, 0.22)
                else:
                    Color(0.63, 0.45, 0.28)
                Rectangle(pos=(obstacle.x, obstacle.y), size=(obstacle.width, obstacle.height))

            for bottle in self.bottles:
                Color(0.12, 0.72, 0.52)
                RoundedRectangle(pos=(bottle.x, bottle.y), size=(bottle.width, bottle.height), radius=[12, 12, 8, 8])
                Color(0.35, 0.88, 0.72)
                Rectangle(pos=(bottle.x + bottle.width * 0.25, bottle.y + bottle.height * 0.78), size=(bottle.width * 0.5, bottle.height * 0.24))
                Color(0.95, 0.77, 0.18)
                Rectangle(pos=(bottle.x + bottle.width * 0.3, bottle.y + bottle.height * 0.98), size=(bottle.width * 0.4, bottle.height * 0.05))

            gun_len = self.width * 0.14
            gun_dx = math.cos(self.gun_angle) * gun_len
            gun_dy = math.sin(self.gun_angle) * gun_len

            Color(0.22, 0.22, 0.26)
            Line(points=[self.gun_x, self.gun_y, self.gun_x + gun_dx, self.gun_y + gun_dy], width=16)
            Color(0.12, 0.12, 0.14)
            Line(points=[self.gun_x + gun_dx * 0.35, self.gun_y + gun_dy * 0.35, self.gun_x + gun_dx * 1.15, self.gun_y + gun_dy * 1.15], width=7)
            Color(0.35, 0.25, 0.18)
            Line(points=[self.gun_x - 8, self.gun_y - 4, self.gun_x - 20, self.gun_y - 42], width=12)

            for bullet in self.bullets:
                Color(0.82, 0.18, 0.15)
                Ellipse(pos=(bullet.x - bullet.radius, bullet.y - bullet.radius), size=(bullet.radius * 2, bullet.radius * 2))

            for particle in self.particles:
                Color(particle.r, particle.g, particle.b, max(0.0, particle.life / 0.5))
                Ellipse(
                    pos=(particle.x - particle.size / 2, particle.y - particle.size / 2),
                    size=(particle.size, particle.size),
                )

            Color(1.0, 1.0, 1.0, 0.22)
            guide_steps = 6
            for step in range(1, guide_steps + 1):
                t = step / (guide_steps + 1)
                dot_x = self.gun_x + (self.crosshair[0] - self.gun_x) * t
                dot_y = self.gun_y + (self.crosshair[1] - self.gun_y) * t
                dot_size = max(3, 8 - step)
                Ellipse(pos=(dot_x - dot_size / 2, dot_y - dot_size / 2), size=(dot_size, dot_size))

            Color(1, 0.2, 0.2, 0.8)
            Line(circle=(self.crosshair[0], self.crosshair[1], 16), width=1.2)
            Line(points=[self.crosshair[0] - 10, self.crosshair[1], self.crosshair[0] + 10, self.crosshair[1]], width=1.2)
            Line(points=[self.crosshair[0], self.crosshair[1] - 10, self.crosshair[0], self.crosshair[1] + 10], width=1.2)

            if not self.game_started or self.paused:
                Color(0.05, 0.08, 0.12, 0.45)
                Rectangle(pos=self.pos, size=self.size)


class GameRoot(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.game = GameWidget(size_hint=(1, 1))
        self.add_widget(self.game)

        self.hud = Label(
            text="",
            size_hint=(1, None),
            height=40,
            pos_hint={"x": 0, "top": 1},
            color=(0.12, 0.12, 0.12, 1),
            bold=True,
        )
        self.add_widget(self.hud)

        self.center = Label(
            text="",
            size_hint=(1, None),
            height=70,
            pos_hint={"center_x": 0.5, "center_y": 0.76},
            color=(0.08, 0.35, 0.7, 1),
            bold=True,
            font_size="28sp",
        )
        self.add_widget(self.center)

        self.summary = Label(
            text="",
            size_hint=(0.86, None),
            height=100,
            pos_hint={"center_x": 0.5, "center_y": 0.63},
            color=(0.1, 0.2, 0.28, 1),
            halign="center",
            valign="middle",
            font_size="17sp",
        )
        self.summary.bind(size=lambda instance, _value: setattr(instance, "text_size", instance.size))
        self.add_widget(self.summary)

        self.menu_panel = FloatLayout(
            size_hint=(0.84, 0.42),
            pos_hint={"center_x": 0.5, "center_y": 0.55},
        )
        self.add_widget(self.menu_panel)

        self.menu_title = Label(
            text="Bottle Shooter",
            size_hint=(1, None),
            height=50,
            pos_hint={"center_x": 0.5, "top": 1.0},
            color=(1, 1, 1, 1),
            bold=True,
            font_size="34sp",
        )
        self.menu_panel.add_widget(self.menu_title)

        self.menu_subtitle = Label(
            text="Drag to aim, release to fire\\nHigh score save hota rahega",
            size_hint=(1, None),
            height=80,
            pos_hint={"center_x": 0.5, "top": 0.74},
            color=(0.92, 0.97, 1.0, 1),
            halign="center",
            valign="middle",
            font_size="18sp",
        )
        self.menu_subtitle.bind(size=lambda instance, _value: setattr(instance, "text_size", instance.size))
        self.menu_panel.add_widget(self.menu_subtitle)

        self.play_button = Button(
            text="Play",
            size_hint=(0.46, 0.22),
            pos_hint={"center_x": 0.5, "y": 0.18},
            background_normal="",
            background_down="",
            background_color=(0.1, 0.58, 0.38, 0.95),
            color=(1, 1, 1, 1),
            bold=True,
        )
        self.play_button.bind(on_release=lambda *_args: self.game.start_game())
        self.menu_panel.add_widget(self.play_button)
        self.menu_panel.bind(pos=self._redraw_menu_panel, size=self._redraw_menu_panel)

        self.status = Label(
            text="",
            size_hint=(1, None),
            height=40,
            pos_hint={"center_x": 0.5, "y": 0.12},
            color=(0.25, 0.2, 0.15, 1),
        )
        self.add_widget(self.status)

        self.reload_button = Button(
            text="Reload",
            size_hint=(0.22, 0.08),
            pos_hint={"x": 0.08, "y": 0.02},
        )
        self.reload_button.bind(on_release=lambda *_args: self.game.reload_level())
        self.add_widget(self.reload_button)

        self.pause_button = Button(
            text="Pause",
            size_hint=(0.18, 0.065),
            pos_hint={"center_x": 0.5, "y": 0.03},
        )
        self.pause_button.bind(on_release=lambda *_args: self.game.toggle_pause())
        self.add_widget(self.pause_button)

        self.restart_button = Button(
            text="Restart",
            size_hint=(0.22, 0.08),
            pos_hint={"right": 0.92, "y": 0.02},
        )
        self.restart_button.bind(on_release=lambda *_args: self.game.restart_game())
        self.add_widget(self.restart_button)

        Clock.schedule_interval(self.sync_labels, 1 / 30)
        Clock.schedule_once(self._redraw_menu_panel, 0)

    def sync_labels(self, _dt):
        self.hud.text = self.game.hud_text
        self.status.text = self.game.status_text
        self.center.text = self.game.center_text
        self.summary.text = self.game.summary_text
        self.summary.opacity = 1 if (self.game.summary_text and (not self.game.game_started or self.game.game_finished or self.game.center_text == "Level fail")) else 0
        self.menu_panel.opacity = 1 if not self.game.game_started else 0
        self.play_button.opacity = 1 if not self.game.game_started else 0
        self.play_button.disabled = self.game.game_started
        self.menu_title.opacity = 1 if not self.game.game_started else 0
        self.menu_subtitle.opacity = 1 if not self.game.game_started else 0
        self.menu_panel.disabled = self.game.game_started
        self.pause_button.text = "Resume" if self.game.paused else "Pause"
        self.pause_button.disabled = not self.game.game_started or self.game.game_finished

    def _redraw_menu_panel(self, *_args):
        self.menu_panel.canvas.before.clear()
        with self.menu_panel.canvas.before:
            Color(0.08, 0.17, 0.24, 0.88)
            RoundedRectangle(pos=self.menu_panel.pos, size=self.menu_panel.size, radius=[28, 28, 28, 28])
            Color(0.18, 0.44, 0.58, 0.25)
            RoundedRectangle(
                pos=(self.menu_panel.x + self.menu_panel.width * 0.03, self.menu_panel.y + self.menu_panel.height * 0.03),
                size=(self.menu_panel.width * 0.94, self.menu_panel.height * 0.94),
                radius=[24, 24, 24, 24],
            )


class BottleGameApp(App):
    def build(self):
        self.title = "Bottle Shooter APK Ready"
        return GameRoot()


if __name__ == "__main__":
    BottleGameApp().run()
