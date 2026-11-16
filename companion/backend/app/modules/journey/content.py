"""Authored content for the complete shared-time reward loop."""

GIFT_TAGS = {
    'flower': ('romance', 'nature'), 'tea': ('daily', 'quiet'),
    'book': ('quiet', 'creative'), 'brush': ('creative', 'daily'),
    'card': ('romance', 'memory'), 'album': ('memory', 'creative'),
    'wind_chime': ('nature', 'quiet'), 'glasses': ('style', 'daily'),
    'hat': ('style', 'nature'), 'casual_outfit': ('style', 'daily'),
    'coat_outfit': ('style', 'quiet'), 'dress_outfit': ('style', 'romance'),
}
TAG_NAMES = {
    'romance': '浪漫心意', 'nature': '自然气息', 'daily': '日常陪伴',
    'quiet': '安静时光', 'creative': '创作灵感', 'memory': '共同纪念', 'style': '穿搭审美',
}
GIFT_SETS = (
    {'id': 'quiet_afternoon', 'name': '安静下午', 'items': ('tea', 'book', 'wind_chime'), 'coin': 30},
    {'id': 'creative_day', 'name': '一起创作', 'items': ('book', 'brush', 'album'), 'coin': 40},
    {'id': 'romantic_letter', 'name': '把心意留下', 'items': ('flower', 'card', 'album'), 'coin': 40},
    {'id': 'style_day', 'name': '日常新装', 'items': ('glasses', 'hat', 'casual_outfit'), 'coin': 60},
    {'id': 'warm_outing', 'name': '暖意出门', 'items': ('coat_outfit', 'hat', 'wind_chime'), 'coin': 60},
    {'id': 'special_day', 'name': '郑重纪念', 'items': ('dress_outfit', 'album', 'card'), 'coin': 100},
)
LEVEL_REWARDS = {
    2: ('角色回礼', '达到第二阶段的好感后，角色可能准备一份永久回礼。'),
    3: ('偏好加倍', '投其所好会额外提高好感与陪伴经验。'),
    4: ('套装纪念', '集齐礼物组合后自动结算套装奖励。'),
    5: ('共同纪念日', '认识 7、30、100、365 天时留下纪念并获得金币。'),
}
RETURN_GIFTS = (
    ('hand_letter', '一封手写信', 'card', '我也想把这一刻好好留下来。谢谢你，让我知道自己被认真惦记着。'),
    ('pressed_flower', '夹好的干花', 'flower', '这朵没有刚才那束漂亮，但我把它留了很久。现在想把它交给你。'),
    ('small_bookmark', '手作书签', 'book', '下次一起看书的时候，就用它夹住我们读到的那一页。'),
    ('tiny_drawing', '一张小画', 'brush', '我画下了今天的一点心情。不是很好看，但只想给你。'),
)
