"""站点说明书 (由 spec 命令自动生成, 可手工编辑)。"""

SITE_SPEC = """被测系统: 被测站点
基础地址: http://127.0.0.1:5000 (由环境变量 SMOKE_BASE_URL 提供, 脚本中读取)
公共导航(所有页面继承): #nav-home(首页, link); #nav-cart(购物车 (), link); #nav-logout(退出, link, 条件渲染); #nav-login(登录, link, 条件渲染); #nav-user(span区域, area, 条件渲染)

页面与路由:
- GET / (app.py): 今日好物; 控件: #product-list(div区域, area); 可用class: .product-grid, .product, .product-name, .product-price, .product-stock, .add-to-cart
- GET,POST /login (app.py): 登录; 控件: #username(用户名, text, 必填); #password(密码, password, 必填); #login-btn(登 录, button); #login-form(form(method=post), form); #login-error(div区域, area); 可用class: .form-error, .hint
- GET /logout (app.py)
- POST /cart/add/<int:product_id> (app.py)
- GET /cart (app.py): 购物车; 控件: #checkout-btn(去结算, button, 条件渲染); #cart-items(div区域, area, 条件渲染); #total-price(div区域, area, 条件渲染); #cart-empty(div区域, area, 条件渲染); 可用class: .cart-item, .cart-item-name, .cart-item-price, .cart-item-subtotal
- GET,POST /checkout (app.py): 确认订单; 控件: #address(收货地址, text, 必填, placeholder=请填写收货地址); #phone(联系电话, text, 必填, placeholder=请填写联系电话); #confirm-order-btn(提交订单, button); #checkout-form(form(method=post), form)
- GET /order/<order_id> (app.py): ✅ 下单成功; 控件: #back-home(返回首页, link); #order-success(div区域, area); #order-id(strong区域, area); 可用class: .order-success

业务规则:
1. 演示账号: admin/admin123, demo/demo123
2. 页面提示信息: 商品不存在
3. 页面提示信息: 请填写收货地址和联系电话
4. 未登录访问受保护页面会跳转到登录页
5. 访问不存在的资源返回 404: 订单不存在
6. 关键表单字段未填写时给出提示并停留在当前页
7. 登录成功后写入 session 并跳转首页
8. 密码为空时，点击登录会显示相应错误提示

测试脚本要求:
1. 使用 Python + pytest + playwright.sync_api
2. 浏览器 fixture 已由 Script/conftest.py 统一提供, 每个测试函数直接声明 page 参数
   即可使用(conftest 已提供 browser / page / base_url 三个 fixture, 会话级只启动一次浏览器),
   **禁止在脚本里重复定义 browser 或 page fixture**
3. 基础地址使用环境变量 SMOKE_BASE_URL 或 base_url fixture
4. 每个用例为普通 def test_xxx, 允许定义辅助函数
5. 断言必须使用 playwright.sync_api.expect 的自动等待断言(如 expect(locator).to_be_visible(),
   to_have_text(), to_have_count() 等), 禁止用 is_visible()/inner_text() 直接断言,
   避免点击后立即断言导致的时序问题
6. 导航/交互后如需等待, 使用 page.wait_for_load_state("networkidle") 或 expect 自动等待
7. 每个用例函数名必须与 cases 中的 func 字段一一对应
"""
