"""Validated, persistent export formats; render jobs keep their own catalog snapshot."""
import re

DEFAULT_FORMATS = [
    dict(id='standard', name='Стандарт', width=1080, height=1080),
    dict(id='marketplace', name='Маркетплейс', width=900, height=1200),
    dict(id='vertical', name='Вертикальный', width=1080, height=1920),
]


def validate_catalog(value):
    if not isinstance(value, list) or not 3 <= len(value) <= 32:
        raise ValueError('В списке должно быть от 3 до 32 размеров.')
    result, ids, names = [], set(), set()
    presets = {item['id']: item for item in DEFAULT_FORMATS}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Некорректный размер видео.')
        key, name = item.get('id'), item.get('name')
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', key) or key in ids:
            raise ValueError('Идентификаторы размеров должны быть уникальны.')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48 or any(ord(c) < 32 for c in name):
            raise ValueError('Укажите название размера от 1 до 48 символов.')
        name = name.strip()
        if name.casefold() in names:
            raise ValueError('Названия размеров должны быть уникальны.')
        width, height = item.get('width'), item.get('height')
        if any(isinstance(n, bool) or not isinstance(n, int) or not 32 <= n <= 8192 or n % 2 for n in (width, height)):
            raise ValueError('Ширина и высота должны быть чётными числами от 32 до 8192 пикселей.')
        if width * height > 33_554_432:
            raise ValueError('Размер кадра не должен превышать 33,5 мегапикселя.')
        if key in presets:
            preset = presets[key]
            if name != preset['name'] or width * preset['height'] != height * preset['width']:
                raise ValueError('Стандартные размеры сохраняют название и пропорции.')
        ids.add(key); names.add(name.casefold())
        result.append(dict(id=key, name=name, width=width, height=height))
    if not presets.keys() <= ids:
        raise ValueError('Стандартные размеры нельзя удалить.')
    return result


def catalog_dimensions(catalog, key):
    if not isinstance(key, str):
        raise ValueError('Неизвестный формат видео.')
    item = next((item for item in catalog if item['id'] == key), None)
    if item is None:
        raise ValueError('Неизвестный формат видео.')
    return item['width'], item['height']
