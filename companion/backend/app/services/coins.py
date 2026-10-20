"""金币外壳。规则在编译好的 coins_box 里，这里只把三个入口交出去。"""
from . import coins_box as _box

CoinError = _box.CoinError
BURN = _box.BURN
heartbeat = _box.heartbeat
balance = _box.balance
pay = _box.pay
redeem = _box.redeem
preview = _box.preview
