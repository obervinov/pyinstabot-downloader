# Интеграция Raw Content Processing в вашу систему

## Быстрый старт

### 1. Конфигурация в Vault

Убедитесь, что у вас есть конфигурация для WebDAV (uploader):

```bash
# Проверьте в Vault
vault kv get configuration/uploader-api
```

### 2. Инициализация в bot.py

Когда вы инициализируете WebUI, передайте параметры для content processing:

```python
from src.modules.webui import WebUI
from src.modules.uploader import Uploader

# ... ваш существующий код ...

# Инициализируйте uploader
uploader = Uploader(database=database, vault=vault)

# Передайте uploader и пути в WebUI
webui = WebUI(
    database=database,
    vault=vault,
    users={'auth': users_auth, 'rate_limited': users_rl},
    uploader=uploader,  # NEW: Для content processing
    raw_content_source_dir='/raw-content',  # NEW: Источник сырого контента
    raw_content_dest_dir='/processed-content',  # NEW: Назначение обработанного контента
    # ... другие параметры ...
)
```

### 3. Структура директорий в WebDAV

Убедитесь, что в вашем WebDAV хранилище существуют директории:

```
/
├── raw-content/          (источник сырого контента)
│   ├── post_123.json     (метаданные в JSON формате)
│   ├── post_456.txt      (метаданные в TXT формате)
│   ├── image1.jpg
│   ├── image2.jpg
│   └── ...
└── processed-content/    (обработанный контент)
    └── (заполнится автоматически после обработки)
```

## Формат метаданных из браузерного расширения

Ваше расширение Firefox может создавать файлы метаданных в `/raw-content/` в формате **JSON** или **TXT**:

### Формат JSON

```json
{
  "post_id": "17999999999999999",
  "username": "testuser",
  "caption": "Awesome post caption here",
  "created_at": "2026-02-21T10:30:45",
  "source": "instagram",
  "files": [
    "instagram_17999999999999999_1.jpg",
    "instagram_17999999999999999_2.jpg",
    "instagram_17999999999999999_3.mp4"
  ]
}
```

### Формат TXT

```txt
post_id=17999999999999999
username=testuser
caption=Awesome post caption here
created_at=2026-02-21T10:30:45
source=instagram
files=[instagram_17999999999999999_1.jpg,instagram_17999999999999999_2.jpg,instagram_17999999999999999_3.mp4]
```

**Синтаксис TXT формата:**
- Один параметр на строку в формате `ключ=значение`
- Массивы указываются в квадратных скобках: `files=[file1.jpg,file2.jpg]`
- Комментарии начинаются с `#` и игнорируются
- Пустые строки игнорируются

**Обязательные поля:**
- `post_id` - Уникальный идентификатор поста
- `source` - Источник ("instagram", "tiktok" и т.д.)
- `files` - Массив имён файлов относящихся к посту

**Необязательные поля:**
- `username` - Имя пользователя
- `caption` - Описание/подпись к посту
- `created_at` - Время создания (ISO 8601 формат)

## Использование Web UI

1. **Откройте Dashboard** - перейдите на `/dashboard`
2. **Найдите секцию "🔄 Process Raw Content"** - она находится после статистики
3. **Нажмите кнопку "Start Processing"**
4. **Смотрите результаты** - система покажет сколько постов обработано, сколько ошибок

## Использование API

### Запустить обработку контента

```bash
curl -X POST http://localhost:8080/api/process-raw-content \
  -H "Cookie: session=<your-session-token>"
```

### Ответ при успехе

```json
{
  "status": "success",
  "message": "Processing complete: 5 processed, 2 skipped, 0 errors",
  "details": {
    "processed_count": 5,
    "skipped_count": 2,
    "error_count": 0,
    "processed_items": [
      {
        "post_id": "17999999999999999",
        "source": "instagram",
        "destination": "/processed-content/instagram/2026-02/testuser/17999999999999999",
        "files_moved": 3
      }
    ],
    "errors": []
  }
}
```

## Расширение функциональности

### Добавление поддержки новой платформы (например TikTok)

1. **Создайте адаптер** в `src/modules/content_processor.py`:

```python
class TiktokRawAdapter:
    def __init__(self, metadata, webdav_client):
        self.metadata = metadata
        self.webdav_client = webdav_client

    def organize(self):
        return {
            'post_id': self.metadata.get('video_id'),
            'source': 'tiktok',
            'username': self.metadata.get('author'),
            'description': self.metadata.get('description'),
            'created_at': self.metadata.get('created_at'),
            'media_count': len(self.metadata.get('files', [])),
            'raw_metadata': self.metadata
        }
```

2. **Зарегистрируйте адаптер** при инициализации RawContentProcessor:

```python
processor = RawContentProcessor(
    webdav_client=webdav_client,
    source_dir='/raw-content',
    dest_dir='/processed-content',
    adapter_map={
        'instagram': InstagramRawAdapter,
        'tiktok': TiktokRawAdapter  # Новый
    }
)
```

## Мониторинг и отладка

### Проверка логов

```bash
# Смотрите логи обработки контента
grep "RawContentProcessor\|ContentProcessor" /var/log/bot.log

# Проверьте ошибки
grep "error\|Error\|ERROR" /var/log/bot.log | grep ContentProcessor
```

### Проверка директорий WebDAV

```bash
# Используйте ваш WebDAV клиент для проверки структуры
# Например, через curl
curl -X PROPFIND http://webdav.example.com/raw-content/
```

### Отладка конкретного поста

Если пост не обрабатывается:

1. Проверьте валидность JSON в файле метаданных
2. Убедитесь что все файлы из массива `files` существуют в той же директории
3. Проверьте права доступа WebDAV
4. Посмотрите логи с полной информацией об ошибке

## Проблемы и решения

### "Content processing is not configured"

**Причина:** WebUI инициализирован без параметра `uploader`

**Решение:**
```python
webui = WebUI(
    # ... другие параметры ...
    uploader=uploader,  # Добавьте это
    raw_content_source_dir='/raw-content',
    raw_content_dest_dir='/processed-content'
)
```

### "Invalid metadata format in file"

**Причина:** Браузерное расширение создало неправильный JSON или TXT

**Решение:**
- Для JSON: Проверьте формат используя jsonlint или подобный инструмент
- Для TXT: Убедитесь что каждая строка в формате `ключ=значение`, массивы в квадратных скобках

### Файлы не движутся в обработанную директорию

**Причина:** Проблема с правами доступа WebDAV

**Решение:** Проверьте что:
- Учёт WebDAV имеет права на чтение/запись в обе директории
- Путь к директориям правильный и совпадает с `raw_content_source_dir` и `raw_content_dest_dir`

## Примеры браузерного расширения

### Firefox Extension (JavaScript)

```javascript
// content-script.js
async function scrapeAndUpload() {
    const postId = document.querySelector('[data-testid="post"]').id;
    const username = document.querySelector('a[href="/' + getUsername() + '"]').href.split('/')[3];
    const caption = document.querySelector('[data-testid="post-caption"]').textContent;

    const metadata = {
        post_id: postId,
        username: username,
        caption: caption,
        created_at: new Date().toISOString(),
        source: 'instagram',
        files: [] // Заполняется при скачивании файлов
    };

    // Отправляем на WebDAV
    const formData = new FormData();
    formData.append('metadata.json', new Blob([JSON.stringify(metadata)], {type: 'application/json'}));
    formData.append('image1.jpg', imageBlob1);
    formData.append('image2.jpg', imageBlob2);

    await fetch('https://webdav.example.com/raw-content/', {
        method: 'POST',
        body: formData
    });
}
```

## Дальнейшее развитие

В будущем можно добавить:
- Сохранение метаданных в базу данных для поиска
- Автоматическая обработка по расписанию
- Веб-интерфейс для редактирования метаданных
- Обнаружение дубликатов
- WebSocket уведомления о ходе обработки в реальном времени
- Поддержка YouTube, TikTok, Twitter и других платформ
