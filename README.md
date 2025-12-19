# 🤖 Telegram Support Bot (Serverless CRM)
There is no need to pay for the server, the bot works for free always
  
**Telegram Support Bot** is a serverless bot for **Yandex Cloud Functions** that turns any Telegram group into a full-fledged Helpdesk/CRM system.

It operates entirely without a dedicated server (free tier eligible). The bot utilizes **Forum Topics** in Telegram Supergroups to manage tickets. A separate topic is created for each new user, keeping conversations organized and isolated.

## ✨ Features

* **Dialog Isolation:** A separate Forum Topic is created for each user in the admin group.
* **Smart Naming:** Topics are named using the user's `Username` or `First Name + Last Name` + `ID`.
* **Info Card:** On the first contact, the bot sends a detailed card with user info (ID, link, name).
* **Media Support:** Supports two-way forwarding of photos, videos, voice messages, files, and stickers.
* **Feedback Mechanism:** User messages are **Forwarded** to the topic, while Admin replies are sent back to the user as **Copies** (appearing as if they came from the bot).
* **Persistent Database:** The "User — Topic" mapping is stored in a JSON file in **Yandex Object Storage** (S3), so data is not lost during function restarts.
* **Admin Commands:** Includes tools to reset user bindings (`/reset`).

## 🛠 Prerequisites

### 1. Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and get your **Token**.
2. Create a new Group in Telegram.
3. **IMPORTANT:** Enable **Topics** in the group settings.
4. Add the bot to the group and promote it to **Administrator** (Must have **Manage Topics** permission).
5. Get the Group ID (usually starts with `-100`).
* *Tip:* Forward any message from the group to [@getmyid_bot](https://t.me/getmyid_bot).



### 2. Yandex Cloud Setup (Object Storage)

1. Create a **Bucket** in Object Storage.
2. Create a **Service Account**.
3. Grant the account the `storage.editor` role.
4. Create a **Static Access Key** for this account. Save the `Key ID` and `Secret Key`.

---

## 🚀 Installation & Deploy (Yandex Cloud Functions)

### Step 1. Create Function

1. Go to **Cloud Functions**.
2. Create a new function (Python).
3. In the editor, create two files: `index.py` and `requirements.txt`.

### Step 2. Code

**File `requirements.txt`:**

```text
boto3

```

**File `index.py`:**
*Copy the code from this repository.*

> ⚠️ **ATTENTION:** Find the `ADMIN_CHAT_ID` variable in the code and insert your group ID there!
> ```python
> ADMIN_CHAT_ID = "-100xxxxxxxxxx" 
> 
> ```
> 
> 

### Step 3. Environment Variables

Add the following variables in the function settings:

| Key | Value | Description |
| --- | --- | --- |
| `BOT_TOKEN` | `12345:AAH...` | Token from BotFather |
| `BUCKET_NAME` | `my-bot-db` | Name of your Bucket in Object Storage |
| `AWS_ACCESS_KEY_ID` | `YCAJ...` | Service Account Key ID |
| `AWS_SECRET_ACCESS_KEY` | `YCO...` | Service Account Secret Key |

*(Optional)* `TG_SECRET` — Secret token for webhook security.

### Step 4. API Gateway Setup

Instead of making the function public directly, we will set up an API Gateway. This is safer and cleaner.

1. Go to **API Gateway** in the Yandex Cloud console.
2. Click **"Create API gateway"**.
3. Name it (e.g., `bot-gateway`).
4. In the **Specification (YAML)** field, delete everything and paste the following code:

```yaml
openapi: 3.0.0
info:
  title: Telegram Bot API
  version: 1.0.0
paths:
  /:
    post:
      x-yc-apigateway-integration:
        type: cloud_functions
        function_id: <INSERT_YOUR_FUNCTION_ID>
        service_account_id: <INSERT_YOUR_SERVICE_ACCOUNT_ID>
      operationId: botHandler

```

> **Important:**
> * Replace `<INSERT_YOUR_FUNCTION_ID>` with the ID of the function you created in Step 1.
> * Replace `<INSERT_YOUR_SERVICE_ACCOUNT_ID>` with the ID of the Service Account (the one with access to S3).
> 
> 

5. Click **Create**.
6. In the list of gateways, find the **Service Domain** (it looks like `https://d5h.......apigw.yandexcloud.net`).
7. Copy this URL. This is your bot's address.

### 🔗 Step 5. Webhook Setup

Now you need to tell Telegram where to send messages.

1. Take the URL from the API Gateway.
2. Insert your data into the link below and open it in your browser:

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=<URL_FROM_API_GATEWAY>

```

*Example:*
`https://api.telegram.org/bot12345:AAF.../setWebhook?url=https://d5hqk12345.apigw.yandexcloud.net`

If you see the message `Webhook was set`, you are ready to go! 🎉

---

## 🎮 Usage

### For Users

The user simply sends a message to the bot in a private chat.

* The bot creates a Topic in the admin group.
* The first message sent is an info card with the client's data.

### For Administrators

1. Go to the created Topic.
2. Simply write a reply — the bot will send it to the user.
3. If the user sends media, you will see it in the topic.

### Admin Commands

These commands only work inside the admin group:

* `/reset` (inside a topic): Unbinds the current user from this topic.
* *Scenario:* You delete the topic manually -> type `/reset` -> the bot "forgets" the old topic. The next message from the user will create a fresh topic.


* `/reset <ID>` (in General or any topic): Unbind a specific user by their Telegram ID.
* `/reset all` (in General or any topic): **Full Database Wipe**. The bot forgets all users and will create new topics for everyone.

---

## 🆘 Troubleshooting

**Error: `Bad Request: the chat is not a forum**`

* You have not enabled "Topics" in the Telegram group settings.

**Error: `Bad Request: not enough rights**`

* The bot is not an Admin, or the "Manage Topics" permission is disabled.

**Error: Bot creates endless topics / doesn't respond**

* Check the Function logs in Yandex Cloud. Most likely an issue with S3 permissions (invalid Access Keys).

## 📄 License

MIT License. Free to use.
