"""Generate the shared-life artwork with the existing local Ark configuration.

Existing files are never overwritten. No credentials are logged.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from pathlib import Path

import httpx
from generate_tarot_seedream import api_key, download_image, generate_once
from generate_wish_art import punch_green
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / 'assets' / 'life'
STYLE = ('高品质手绘动画电影背景，温柔细腻的笔触，暖琥珀与奶油色，'
         '舒适安静，真实材质与柔和自然光，无人物、无文字、无水印、无边框。')
JOBS = {
    'room.jpg': '横构图，一间温暖小小的陪伴工作室，正面视角，中央木桌和椅子，左边一扇大窗，右边书架与相框，窗外柔和日光，桌面整洁，室内植物。' + STYLE,
    'gifts.jpg': '横构图，木桌上精心陈列一朵粉色小花、一杯热茶、一本旧书、画笔和信封，物品真实有层次，温柔日光。' + STYLE,
    'activities.jpg': '横构图，宁静的雨天窗边，两杯茶、画本和画笔摆在桌上，窗玻璃有雨滴，室内暖灯亮着，讲述一起度过的时光。' + STYLE,
    'apartment.jpg': '横构图，城市温馨小公寓客厅，落地窗外傍晚城市灯光，左侧柔软沙发，中央茶几与木地板，适合角色站在中央，留出清晰空间。' + STYLE,
    'garden.jpg': '横构图，温暖的庭院小楼室内，推开窗可见花园，木质书桌与浅色墙面，午后阳光，中央留出人物站立位置。' + STYLE,
    'villa.jpg': '横构图，宁静的海边独栋房屋客厅，大窗望向日落大海，浅色木家具、纱帘、沙发，中央留有角色位置。' + STYLE,
    'castle.jpg': '横构图，梦幻海边城堡的明亮起居室，拱窗通向碧蓝大海，柔软织物与金色细节，温柔宜居，中央留有角色位置。' + STYLE,
    'cafe.jpg': '横构图，窗边舒适小咖啡馆，桌上有两杯咖啡和点心，窗外是安静街道，中央留有角色位置。' + STYLE,
    'park.jpg': '横构图，晴朗安静的城市公园小道，远处花草和一辆停放的复古自行车，中央留有角色位置。' + STYLE,
    'rental.jpg': '横构图，小而温馨的城市出租屋客厅，木桌、布沙发和可摆放装饰的空墙，柔和下午阳光，中央留出人物位置。' + STYLE,
    'kitchen.jpg': '横构图，温暖整洁的小家厨房，木质料理台、灶台和餐桌，暖色灯光，中央留出角色位置。' + STYLE,
    'restaurant.jpg': '横构图，温馨的原创家常餐厅，双人木桌与餐具、暖色吊灯，中央留出角色位置，不出现品牌。' + STYLE,
    'hotpot_restaurant.jpg': '横构图，舒适的原创火锅店，双人餐桌中央的热锅冒着蒸汽，窗外夜色，中央留出角色位置。' + STYLE,
    'teashop.jpg': '横构图，原创茶饮店内部，木质吧台、暖光、干净的双人座位，中央留出角色位置，不出现品牌或字。' + STYLE,
    'garage.jpg': '横构图，温暖明亮的家用车库，整洁地面和木柜，右侧留出车辆展示空间，中央留出角色位置。' + STYLE,
    'coast.jpg': '横构图，海边散步道，日落、海浪和远处灯塔，木栈道通向海边，中央留出角色位置。' + STYLE,
    'camp.jpg': '横构图，湖边露营地，空帐篷、小桌和暖灯，傍晚天空，中央留出角色位置。' + STYLE,
    'wardrobe.jpg': '横构图，温暖的衣帽间，开放式衣柜、穿衣镜、木地板和柔和光线，中央留出角色试穿位置。' + STYLE,
}
JOBS.update({
    'studio.jpg': '横构图，明亮紧凑的阳光单间，奶油色墙面，浅木书桌，小沙发，整洁开放式厨房，大窗投下清晨阳光，中央留出角色位置。' + STYLE,
    'loft.jpg': '横构图，挑高城市阁楼，夹层楼梯、砖墙、深色木地板与落地窗，夜幕城市灯光，中央留出角色位置。' + STYLE,
    'courtyard.jpg': '横构图，四季庭院住宅的起居室，推拉玻璃门外是花木与石径，木质家具，柔和春日光线，中央留出角色位置。' + STYLE,
    'forest_home.jpg': '横构图，林间小筑室内，木梁、壁炉、阅读椅与大窗外的森林薄雾，温暖灯光，中央留出角色位置。' + STYLE,
    'lake_home.jpg': '横构图，湖畔居所客厅，宽阔玻璃窗外是平静湖面和远山，浅木家具与蓝灰织物，中央留出角色位置。' + STYLE,
    'seaside_house.jpg': '横构图，海风住宅的明亮客厅，白墙、藤编家具、纱帘被海风轻拂，窗外碧海，中央留出角色位置。' + STYLE,
    'sky_home.jpg': '横构图，云端观景居所，高层全景玻璃窗俯瞰云海与城市，精致现代家具，金色晨光，中央留出角色位置。' + STYLE,
})
PROPS = {
    'flower': '一束粉色小花，系着米白色丝带',
    'tea': '一杯冒着热气的暖琥珀色红茶，白瓷茶杯和茶碟',
    'book': '一本奶油色布面精装书，书脊有细腻的金色装饰',
    'brush': '一支漂亮的木柄画笔，刷毛沾着暖红色颜料',
    'card': '一只奶油白的信封和小卡片，红色蜡封，无任何文字',
    'lamp': '一盏复古黄铜小台灯，奶油色灯罩，灯光温暖',
    'picture': '一个复古木质小相框，里面是一幅抽象的暖色风景',
    'hotpot': '一锅精致的番茄汤火锅，旁边整齐摆着蔬菜和肉片，暖色陶瓷餐具',
    'noodles': '一碗热气腾腾的家常面，陶瓷碗与一双木筷子',
    'cake': '一块草莓奶油蛋糕放在白瓷盘里，旁边一只小叉子',
    'bicycle': '一辆奶油白色复古自行车，侧面，完整的两个轮子与车架',
    'car': '一辆原创的奶油白色小型电动汽车，三分之二侧面，造型圆润，无品牌标识',
    'coffee': '一杯拿铁咖啡，奶油白瓷杯和碟，细腻拉花',
    'milk_tea': '一杯琥珀色珍珠奶茶，透明杯和吸管，杯身无品牌、无任何文字',
    'fruit_tea': '一杯暖红色水果茶，透明玻璃杯和橙片',
    'home_dish': '一份色彩温暖的家常炒菜与白米饭，陶瓷餐盘和木筷',
    'dessert': '一盘精致的草莓布丁和小银勺',
    'scooter': '一辆原创奶油白电动踏板车，完整车身，三分之二侧面，无商标',
    'fuel_car': '一辆原创暖灰色汽油轿车，完整车身，三分之二侧面，无品牌标识',
    'camper': '一辆原创米白色小型房车，完整车身，三分之二侧面，无商标',
    'casual_outfit': '一套中性休闲服装平铺展示，包括米白衬衫、棕色长裤与鞋，不含人体',
    'dress_outfit': '一套暖粉色长袖连衣裙与鞋子平铺展示，不含人体',
    'coat_outfit': '一套深蓝色长外套、浅色上衣和长裤平铺展示，不含人体',
    'glasses': '一副精致的玳瑁色圆框眼镜，独立摆放',
    'hat': '一顶米白色柔软针织帽，独立摆放',
    'album': '一本暖棕色精装相册，书脊和封面有细金纹，无文字',
    'wind_chime': '一串精致的浅金色风铃，悬挂，完整可见',
}
PROPS.update({
    'tomato_noodles': '一碗番茄鸡蛋面，红亮番茄汤、金黄鸡蛋和青葱，陶瓷碗与木筷',
    'beef_noodles': '一碗炖牛肉面，大块软烂牛肉、清亮汤汁、面条与青菜，陶瓷碗与木筷',
    'mushroom_noodles': '一碗菌菇面，多种棕色菌菇、清汤和面条，陶瓷碗与木筷',
    'rice_set': '完整家常饭套餐，白米饭、两道家常菜和小碗汤，暖色陶瓷餐具',
    'braised_pork': '一份红烧肉饭，油亮红烧肉、白米饭和少量时蔬，陶瓷餐盘',
    'vegetable_set': '一份时蔬小炒套餐，多彩新鲜蔬菜、白米饭和清汤，陶瓷餐具',
    'curry_rice': '一盘金黄咖喱饭，软烂土豆胡萝卜与米饭，精致陶瓷盘和勺子',
    'tomato_pot': '一锅番茄火锅，红亮番茄汤底，周围整齐摆放肉片和蔬菜',
    'mushroom_pot': '一锅菌菇火锅，清亮菌汤与多种菌菇，周围整齐摆放蔬菜和豆腐',
    'spicy_pot': '一锅香辣红汤火锅，红油辣椒与香料，周围整齐摆放肉片和蔬菜',
    'celebration_cake': '一只完整的小型庆祝蛋糕，奶油与浆果装饰，一根未点燃的蜡烛，无文字',
    'cheesecake': '一块金黄色芝士蛋糕，细腻切面，白瓷盘与甜点叉',
    'chocolate_cake': '一块深棕色巧克力蛋糕，巧克力淋面与浆果，白瓷盘与甜点叉',
    'pudding': '一份焦糖布丁，琥珀色焦糖顶层，玻璃小碟与银色小勺',
    'fruit_parfait': '一杯水果芭菲，草莓、蓝莓、芒果、酸奶与谷物分层，透明高脚杯',
    'tiramisu': '一块提拉米苏，可可粉表面和清晰奶油层次，白瓷盘与甜点叉',
    'americano': '一杯黑咖啡，深琥珀色液面，简洁白瓷杯与杯碟',
    'cappuccino': '一杯卡布奇诺，丰厚细腻奶泡和少量可可粉，白瓷杯与杯碟',
    'mocha': '一杯摩卡咖啡，巧克力色咖啡、奶油顶与可可碎，透明耐热杯',
    'pearl_tea': '一杯珍珠奶茶，琥珀色茶汤、黑糖珍珠和透明杯，无品牌无文字',
    'oolong_milk': '一杯乌龙奶茶，浅茶褐色饮品、透明杯和茶叶小装饰，无品牌无文字',
    'peach_tea': '一杯桃桃果茶，粉橙色茶汤、新鲜桃片和冰块，透明杯，无品牌无文字',
    'lemon_tea': '一杯柠檬果茶，金黄色茶汤、多片柠檬和冰块，透明杯，无品牌无文字',
    'afternoon_tea': '双人下午茶架，三层托盘陈列小蛋糕、司康和水果，旁边两只茶杯',
    'city_bike': '一辆现代城市自行车，奶油白车架、挡泥板与前置小篮，完整侧面',
    'retro_bike': '一辆复古自行车，酒红色弯梁车架、棕色皮座与藤编前篮，完整侧面',
    'folding_bike': '一辆紧凑折叠自行车，银灰车架、小轮径和清晰折叠结构，完整侧面',
    'touring_bike': '一辆旅行自行车，深蓝车架、后货架、驮包与水壶架，完整侧面',
    'city_scooter': '一辆现代城市电动踏板车，米白色车身、简洁前灯和坐垫，完整三分之二侧面',
    'retro_scooter': '一辆复古电动踏板车，暖橙色圆润车身、圆形前灯，完整三分之二侧面',
    'touring_scooter': '一辆旅行电动踏板车，深蓝车身、风挡与后置储物箱，完整三分之二侧面',
    'mini_ev': '一辆原创迷你电动汽车，淡黄色短车身、圆润车灯，完整三分之二侧面，无商标',
    'city_ev': '一辆原创城市电动轿车，珍珠白流线车身，完整三分之二侧面，无商标',
    'sport_ev': '一辆原创运动电动轿车，深红低趴流线造型，完整三分之二侧面，无商标',
    'touring_ev': '一辆原创旅行电动轿车，雾蓝色旅行车造型与宽大后备箱，完整三分之二侧面，无商标',
    'premium_ev': '一辆原创豪华电动轿车，香槟金优雅长车身与精致轮毂，完整三分之二侧面，无商标',
    'compact_car': '一辆原创紧凑燃油轿车，暖灰色实用车身，完整三分之二侧面，无商标',
    'classic_car': '一辆原创经典燃油轿车，墨蓝色复古车身与镀铬细节，完整三分之二侧面，无商标',
    'sport_car': '一辆原创运动燃油轿车，亮橙色动感车身，完整三分之二侧面，无商标',
    'executive_car': '一辆原创行政燃油轿车，黑色修长车身与低调精致细节，完整三分之二侧面，无商标',
    'family_van': '一辆原创家庭面包车，米白色方正车身与大侧窗，完整三分之二侧面，无商标',
    'weekend_van': '一辆原创周末露营车，沙色车身、车顶行李架与遮阳篷，完整三分之二侧面，无商标',
    'touring_van': '一辆原创长途旅行车，深蓝车身、抬高车顶与侧面小窗，完整三分之二侧面，无商标',
    'coast_van': '一辆原创海岸旅行车，浅蓝与奶油白双色车身、车顶冲浪板架，完整三分之二侧面，无商标',
    'flagship_van': '一辆原创旗舰旅行车，香槟银大型车身、精致侧窗与车顶设备，完整三分之二侧面，无商标',
})

BLUE_PROPS = {
    'plant': '一盆枝叶繁茂的绿色小盆栽，陶瓷花盆，完整展示',
}

def punch_blue(path: Path) -> None:
    """Remove the blue backdrop while retaining green leaves."""
    image = Image.open(path).convert('RGBA')
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            score = blue - max(red, green)
            if score > 36 and blue > 80:
                pixels[x, y] = (0, 0, 0, 0)
            elif score > 10 and blue >= red and blue >= green:
                opacity = int(max(0, min(255, (1 - (score - 10) / 36) * alpha)))
                pixels[x, y] = (red, green, min(blue, max(red, green)), opacity)
    image.save(path, 'PNG')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='+', help='Only generate these filenames')
    options = parser.parse_args()
    key = api_key()
    OUT.mkdir(parents=True, exist_ok=True)
    def run(job):
        name, prompt, key_color = job
        path = OUT / name
        if path.exists():
            return f'{name}: already exists'
        with httpx.Client(trust_env=False) as client:
            url = generate_once(client, key, prompt, 'doubao-seedream-5-0-pro-260628', '2K')
            download_image(client, url, path)
        if key_color:
            (punch_blue if key_color == 'blue' else punch_green)(path)
            im = Image.open(path)
            im.thumbnail((512, 512), Image.Resampling.LANCZOS)
            im.save(path, optimize=True)
        else:
            with Image.open(path) as im:
                if im.format != 'JPEG':
                    im.convert('RGB').save(path, format='JPEG', quality=92)
        return f'{name}: generated'
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [(name, prompt, '') for name, prompt in JOBS.items()]
        jobs += [(f'{name}.png', f'{obj}。主体完整居中，四周留白，纯绿色背景 #00ff00，不要绿色物体、不要文字、不要边框、不要水印，精致温暖的动画电影道具插画。', 'green') for name, obj in PROPS.items()]
        jobs += [(f'{name}.png', f'{obj}。主体完整居中，四周留白，纯蓝色背景 #0000ff，不要蓝色物体、不要文字、不要边框、不要水印，精致温暖的动画电影道具插画。', 'blue') for name, obj in BLUE_PROPS.items()]
        if options.only:
            jobs = [job for job in jobs if job[0] in options.only]
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            print(future.result(), flush=True)

if __name__ == '__main__':
    main()
