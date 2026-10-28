# Audio Triggers Guide

Tài liệu này cập nhật lại cơ chế âm thanh hiện tại của dự án Open-J. Cấu trúc âm thanh hiện có tập trung vào `ui/audio_manager.py`, `core/event_bus.py` và các điểm phát sự kiện trong `ui/host_controller.py` và `ui/tv_display.py`.

## Cơ chế hiện tại

`AudioManager` là singleton, nên trong toàn app chỉ có một thể hiện âm thanh duy nhất. Nó lắng nghe tín hiệu từ `event_bus.play_sound_event` và phát file tương ứng.

Các nguyên tắc chính:

- `AudioManager` kế thừa `QObject`
- `event_bus.play_sound_event` là signal `Signal(str)`
- file âm thanh được map theo key trong `sound_files`
- `.wav` thường dùng `QSoundEffect`
- music dài hoặc file nén dùng `QMediaPlayer`
- `play_file()` được dùng cho preview trong settings

---

## Chuyển tiếp sự kiện âm thanh

### 1) EventBus và AudioManager

Trong `core/event_bus.py`:

```python
event_bus.play_sound_event = Signal(str)
```

Trong `ui/audio_manager.py`:

```python
event_bus.play_sound_event.connect(self.play_sound)
```

Nói cách khác, mọi nơi trong app chỉ cần gọi:

```python
event_bus.play_sound_event.emit("board_fill")
```

và `AudioManager` sẽ tìm đúng file âm thanh theo key tương ứng.

---

## Bảng trigger âm thanh thực tế

| Trigger key | Nơi phát | Mô tả |
|---|---|---|
| `board_fill` | `ui/tv_display.py` → `start_board_fill()` | phát khi board fill random được kích hoạt |
| `daily_double` | `ui/tv_display.py` → `_on_zoom_animation_finished()` | âm hiệu Daily Double |
| `think_30s` | `ui/host_controller.py` → `_on_start_30s()` | bắt đầu timmer 30s final |
| `timeout` | `ui/host_controller.py` → `_on_host_timer_5s_tick()` | hết giờ trả lời 5s |
| `wrong` | `ui/host_controller.py` → `_adjust_score()` / final resolve | âm báo trả lời sai |
| `round_category_intro` | `ui/tv_display.py` → `handle_final_step(step=1)` | âm hiệu giới thiệu category vòng cuối |
| `final_category_intro` | `ui/tv_display.py` → `handle_final_step(step=2)` | âm hiệu mời nhập wager / category vòng cuối |
| `outro_music` | `ui/tv_display.py` → `handle_standby_outro_music()` | nhạc kết thúc / standby |

---

## Ví dụ phát âm thanh trong code

### Board fill

```python
@Slot()
def start_board_fill(self):
    self.show_blank_board()
    all_coords = [(c, r) for c in range(6) for r in range(5)]
    random.shuffle(all_coords)
    self.fill_queue = all_coords
    event_bus.play_sound_event.emit("board_fill")
    self.fill_timer.start()
```

### Final timer

```python
def _on_start_30s(self):
    self.final_timer_seconds = 30
    event_bus.trigger_final_step.emit(4, clue_data)
    event_bus.play_sound_event.emit("think_30s")
    self.final_timer.start(1000)
```

### Timeout

```python
def _on_host_timer_5s_tick(self):
    self.host_timer_remaining_ms = max(0, self.host_timer_remaining_ms - 100)
    if self.host_timer_remaining_ms <= 0:
        self.host_timer_5s.stop()
        event_bus.play_sound_event.emit("timeout")
```

### Wrong answer

```python
def _adjust_score(self, player_id, points, is_correct):
    if is_correct:
        self.s_engine.add_correct(player_id, points)
    else:
        self.s_engine.add_incorrect(player_id, points)
        self.audio_manager.stop_all()
        event_bus.play_sound_event.emit("wrong")
```

---

## Mapping tương thích ngược

Trong `AudioManager.play_sound()` có mapping mặc định để giữ tương thích với tên cũ:

```python
canonical_map = {
    "fill": "board_fill",
    "think_music": "think_30s",
    "time_out": "timeout",
    "category_intro": "final_category_intro",
}
```

Điều này giúp code cũ vẫn hoạt động nếu gọi tên biến cũ, nhưng hệ thống hiện đại nên ưu tiên dùng key chuẩn mới.

---

## Cách `AudioManager` xử lý file

`AudioManager` dùng các phương thức sau:

- `_resolve_sound_path(file_or_path)`
  - tìm đường dẫn file tương ứng trong project
- `set_sound_file(event_key, file_path)`
  - gán file cho key âm thanh
- `load_from_dict(sounds_dict)`
  - đồng bộ từ theme config
- `play_sound(sound_key)`
  - phát âm thanh theo key
- `play_file(file_path)`
  - phát preview từ settings

---

## Mẹo debug âm thanh

Nếu âm thanh không phát:

1. Kiểm tra key đã emit có khớp với `sound_files` hay không.
2. Kiểm tra file thật sự tồn tại trong `ui/assets/sounds` hoặc đường dẫn được resolve đúng.
3. Kiểm tra `event_bus.play_sound_event.connect(self.play_sound)` đã được kết nối chưa.
4. Nếu dùng key cũ như `time_out`, `think_music`, `fill`, nó sẽ được canonicalize vào key mới.

---

## Tóm tắt nhanh

Hệ thống âm thanh hiện tại không phụ thuộc vào UI trực tiếp. UI chỉ gọi `event_bus.play_sound_event.emit(key)`, còn `AudioManager` mới là nơi quyết định phát file nào. Đây là cách tốt để tránh duplicate sound, đồng thời dễ quản lý theme và custom sound binding cho từng event.

Nếu cần thêm âm thanh mới, hãy:

1. thêm file vào `ui/assets/sounds/`
2. gán key trong theme hoặc gọi `event_bus.play_sound_event.emit("your_key")`
3. đảm bảo `AudioManager` có thể resolve đường dẫn và phát đúng định dạng

