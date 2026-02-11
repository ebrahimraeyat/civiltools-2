---
id: licensing
title: Licensing
title_fa: مجوز نرم‌افزار
context: help.licensing
order: 50
---

# Licensing & Activation

## Trial Period

On first launch, civilTools grants a **30-day free trial** with full
functionality. The trial countdown starts from the first execution date.

The remaining trial days are shown in the title bar:
```
civilTools 1.0 — Trial (25 days remaining)
```

## Activation

When the trial expires (or if you want to activate immediately):

1. The **Activation Dialog** appears on startup
2. Note your **Machine ID** (displayed in the dialog)
3. Provide the Machine ID to your administrator
4. Enter the **Serial Key** received (format: `CT-XXXXX-XXXXX-XXXXX-XXXXX`)
5. Click **Activate**

After successful activation:
```
civilTools 1.0 — Licensed
```

## Machine ID

The Machine ID is a unique hardware fingerprint generated from:
- CPU identifier
- Disk serial number
- Computer hostname
- Network adapter MAC address

> **Note**: If you change major hardware components, a new serial key
> may be required.

## License File

License data is stored locally at:
```
%LOCALAPPDATA%\civilTools\civilTools\license.json
```

Do not modify this file manually — it will invalidate the license.

## Troubleshooting

| Issue                          | Solution                          |
|--------------------------------|-----------------------------------|
| "License expired"              | Contact admin for a new serial    |
| "Invalid serial key"           | Ensure correct Machine ID was used|
| Trial not starting             | Delete license.json and restart   |
| Hardware changed               | Request new serial with new ID    |
