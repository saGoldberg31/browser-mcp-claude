# Browser MCP for Claude and other models

هذا خادم MCP بعيد يوفّر أدوات متصفح عامة عبر Playwright وStreamable HTTP. لا يعتمد على Claude داخل الخادم؛ يمكن لأي عميل يدعم MCP عبر HTTPS استخدامه، بما في ذلك Claude، أو طبقة وسيطة تستعمل Gemini أو OpenAI أو نموذجًا محليًا.

> الخادم يفتح الصفحات ويقرأها ويعبئ الحقول غير الحساسة، لكنه يمنع حقول كلمات المرور والملفات والإرسال النهائي وعمليات الدفع أو الحذف.

## النشر على Replit

استورد هذا المستودع إلى Replit باستخدام Docker، ثم اختر Reserved VM أو خدمة تعمل باستمرار. أضف المتغيرات التالية في **Secrets**:

| Key | Value |
| --- | --- |
| `MCP_AUTH_TOKEN` | رمز طويل عشوائي لمصادقة Claude مع الخادم |
| `BROWSER_HEADLESS` | `true` |
| `MAX_PAGE_TEXT` | `12000` |

لا تضع كلمات المرور أو رموز التحقق أو مفاتيح المواقع داخل GitHub أو الكود.

بعد النشر يصبح endpoint هو:

`https://YOUR-REPL-DOMAIN/mcp`

ويجب أن يكون عامًا عبر HTTPS؛ Claude يتصل بالخادم من بنية Anthropic السحابية، وليس من هاتفك المحلي.

## ربط Claude Web

في Claude على الهاتف افتح **Customize → Connectors → + → Add custom connector**، وأدخل رابط `/mcp`. إذا طلبت الواجهة OAuth Client ID/Secret فلا تضع `MCP_AUTH_TOKEN` في تلك الخانات؛ هذه الخانات تخص OAuth. استخدم آلية المصادقة التي يعرضها Claude للحساب، أو نفّذ الربط عبر Claude API إذا كان الخادم يحتاج Bearer token مباشرًا.

بعد الإضافة فعّل الموصل في المحادثة من **+ → Connectors**. ابدأ بأوامر قراءة فقط مثل فتح صفحة عامة وأخذ لقطة نصية. راجع كل طلب أداة قبل السماح به.

## تعدد النماذج

خادم MCP لا يفرض نموذجًا. Claude أو Gemini أو OpenAI أو أي نموذج آخر يدعم MCP هو العميل الذي يقرر استدعاء الأدوات. يمكن تغيير النموذج دون تعديل Playwright أو خادم MCP.

## أدوات الخادم

- `browser_open(url)`: فتح صفحة HTTP(S) عامة.
- `browser_snapshot()`: قراءة الصفحة الحالية وعرض مراجع العناصر التفاعلية.
- `browser_click(ref)`: النقر على عنصر غير نهائي.
- `browser_fill(ref, value)`: تعبئة حقل نصي غير حساس.
- `browser_select(ref, label_or_value)`: اختيار عنصر من قائمة.
- `browser_back()`: العودة صفحة واحدة.
- `browser_close()`: إغلاق جلسة المتصفح.

## القيود الأمنية

الخادم يرفض التشغيل إذا لم يكن `MCP_AUTH_TOKEN` مضبوطًا. يجب تشغيله خلف HTTPS عام، وتقييد الوصول إلى المواقع والبيانات بحسب الحاجة. لا تستخدمه لتجاوز CAPTCHA أو ضوابط المواقع، ولا تمنح Claude صلاحية تلقائية لعمليات شراء أو حذف أو إرسال. أضف OAuth حقيقيًا قبل استخدامه مع حسابات إنتاجية.

## مراجع

- [Claude custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Streamable HTTP specification](https://modelcontextprotocol.io/specification/draft/basic/transports/streamable-http)
- [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp)
