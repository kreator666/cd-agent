> ## Documentation Index
> Fetch the complete documentation index at: https://docs.anyway.sh/llms.txt
> Use this file to discover all available pages before exploring further.

# Webhook 投递

> 接收、验证、去重并处理已签名的交易事件。

请在 **Business 个人菜单 → 开发者 → Webhook** 中创建和管理 Webhook 端点。

## 验证公钥

获取并缓存 Anyway 的 Ed25519 公钥：

```bash theme={null}
curl https://api.anyway.sh/v1/webhooks/signing-key
```

```json theme={null}
{
  "keyId": "default",
  "algorithm": "ed25519",
  "publicKey": "whpk_<base64 public key>",
  "keys": [{
    "kty": "OKP",
    "use": "sig",
    "crv": "Ed25519",
    "kid": "default",
    "x": "<base64url public key>",
    "alg": "EdDSA"
  }]
}
```

`publicKey` 是带前缀的原始公钥表示，`keys` 是等价的 JWKS 表示。投递信封遵循 Standard Webhooks，并使用非对称 Ed25519（`v1a`）签名。如果密钥轮换后验证开始失败，请刷新缓存公钥。

## 事件

当前事件包括：

| 事件                     | 含义              |
| ---------------------- | --------------- |
| `order.pending`        | 订单已存在，但付款尚未确认   |
| `order.paid`           | 付款已确认，可以执行履约    |
| `order.failed`         | 付款尝试失败          |
| `subscription.created` | 客户订阅已创建         |
| `subscription.updated` | 当前周期或计划取消信息发生变化 |
| `subscription.expired` | 订阅已过期           |
| `subscription.ended`   | 订阅进入最终结束状态      |

端点未选择任何事件时，会订阅全部受支持事件。只有验证通过的 `order.paid` 才能触发履约。
周期末取消会通过 `subscription.updated` 报告；在 `subscription.ended` 之前，请使用
`cancelAtPeriodEnd` 和 `currentPeriodEnd` 表示计划取消状态。

## 投递请求头与签名内容

| 请求头                 | 含义                                              |
| ------------------- | ----------------------------------------------- |
| `webhook-id`        | 稳定的逻辑事件 ID 和幂等密钥；同一事件重试时保持不变                    |
| `webhook-timestamp` | Unix 秒级时间戳                                      |
| `webhook-signature` | Standard Webhooks 格式的 `v1a,<base64 Ed25519 签名>` |

签名覆盖以下精确字节序列：

```text theme={null}
webhook-id.webhook-timestamp.raw-body
```

解析 JSON 之前，必须使用原始请求体验证。请拒绝过期时间戳和未知签名。

## 验证 Ed25519 签名

<CodeGroup>
  ```javascript Node.js theme={null}
  import express from "express";
  import { createPublicKey, verify as verifySignature } from "node:crypto";

  const signingKeyResponse = await fetch("https://api.anyway.sh/v1/webhooks/signing-key");
  if (!signingKeyResponse.ok) throw new Error("Unable to load Anyway signing keys");
  const jwks = await signingKeyResponse.json();
  const verificationKeys = jwks.keys.map((jwk) =>
    createPublicKey({ key: jwk, format: "jwk" }),
  );

  function verifyAnywayWebhook(rawBody, headers) {
    const id = headers["webhook-id"];
    const timestamp = headers["webhook-timestamp"];
    const signatureHeader = headers["webhook-signature"];
    if (!id || !timestamp || !signatureHeader) throw new Error("Missing webhook headers");

    const timestampSeconds = Number(timestamp);
    if (!Number.isSafeInteger(timestampSeconds) ||
        Math.abs(Math.floor(Date.now() / 1000) - timestampSeconds) > 300) {
      throw new Error("Stale webhook timestamp");
    }

    const signedContent = Buffer.concat([
      Buffer.from(`${id}.${timestamp}.`, "utf8"),
      rawBody,
    ]);
    const valid = signatureHeader.split(" ").some((versionedSignature) => {
      const [version, encodedSignature] = versionedSignature.split(",", 2);
      if (version !== "v1a" || !encodedSignature) return false;
      try {
        const signature = Buffer.from(encodedSignature, "base64");
        return verificationKeys.some((key) =>
          verifySignature(null, signedContent, key, signature),
        );
      } catch {
        return false;
      }
    });
    if (!valid) throw new Error("Invalid webhook signature");
    return JSON.parse(rawBody.toString("utf8"));
  }

  const app = express();

  app.post("/webhooks/anyway", express.raw({ type: "application/json" }), (req, res) => {
    let event;
    try {
      event = verifyAnywayWebhook(req.body, {
        "webhook-id": req.header("webhook-id"),
        "webhook-timestamp": req.header("webhook-timestamp"),
        "webhook-signature": req.header("webhook-signature"),
      });
    } catch {
      return res.sendStatus(401);
    }

    enqueueIdempotently(req.header("webhook-id"), event);
    return res.sendStatus(204);
  });
  ```

  ```python Python theme={null}
  # pip install cryptography
  import base64
  import json
  import time
  from urllib.request import urlopen

  from cryptography.exceptions import InvalidSignature
  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

  def decode_base64url(value):
      return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

  with urlopen("https://api.anyway.sh/v1/webhooks/signing-key", timeout=5) as response:
      jwks = json.load(response)

  verification_keys = [
      Ed25519PublicKey.from_public_bytes(decode_base64url(jwk["x"]))
      for jwk in jwks["keys"]
  ]

  def verify_anyway_webhook(raw_body, headers):
      webhook_id = headers.get("webhook-id")
      timestamp = headers.get("webhook-timestamp")
      signature_header = headers.get("webhook-signature")
      if not webhook_id or not timestamp or not signature_header:
          raise ValueError("Missing webhook headers")

      timestamp_seconds = int(timestamp)
      if abs(int(time.time()) - timestamp_seconds) > 300:
          raise ValueError("Stale webhook timestamp")

      signed_content = f"{webhook_id}.{timestamp}.".encode() + raw_body
      for versioned_signature in signature_header.split():
          try:
              version, encoded_signature = versioned_signature.split(",", 1)
              if version != "v1a":
                  continue
              signature = base64.b64decode(encoded_signature, validate=True)
              for key in verification_keys:
                  try:
                      key.verify(signature, signed_content)
                      return json.loads(raw_body)
                  except InvalidSignature:
                      pass
          except (ValueError, TypeError):
              continue
      raise InvalidSignature("Invalid webhook signature")


  @app.post("/webhooks/anyway")
  def anyway_webhook():
      try:
          event = verify_anyway_webhook(request.get_data(), request.headers)
      except (InvalidSignature, ValueError):
          return ("", 401)

      enqueue_idempotently(request.headers["webhook-id"], event)
      return ("", 204)
  ```
</CodeGroup>

## 载荷

签名后的信封包含 `type`、RFC 3339 `timestamp`、`apiVersion`、端点身份，以及与事件类型对应的
`data.order` 或 `data.subscription`。

重要订单字段包括：

| 字段                                     | 含义                            |
| -------------------------------------- | ----------------------------- |
| `orderId`、`orgId`                      | Anyway 订单和组织                  |
| `merchantReference`、`merchantMetadata` | 你的关联值；按不可信字符串处理               |
| `status`、`provider`                    | 标准付款状态和支付渠道                   |
| `amountCents`、`currency`               | 最小单位金额和小写结算币种                 |
| `product`                              | 可选产品 `id` 和 `name`            |
| `paymentLinkId`                        | 已知时的来源付款链接                    |
| `crypto`                               | 可选 CAIP 区块链标识、资产、付款方、收款方和交易来源 |
| `originalOrderId`                      | 适用时关联的原始订单                    |
| `providerSubscriptionId`               | 适用时的付款渠道订阅归属                  |
| `createdAt`、`updatedAt`                | RFC 3339 UTC 时间戳              |

如果付款链接包含 `merchant_reference=PUR_456&user_id=USR_123&source=web`，订单事件会返回
相同的值：

```json theme={null}
{
  "type": "order.paid",
  "data": {
    "order": {
      "orderId": "ORD_EXAMPLE",
      "merchantReference": "PUR_456",
      "merchantMetadata": {
        "merchant_reference": "PUR_456",
        "user_id": "USR_123",
        "source": "web"
      },
      "status": "PAID"
    }
  }
}
```

Webhook 签名覆盖包括 `merchantMetadata` 在内的完整原始请求体。签名验证只能证明载荷由
Anyway 投递，并不会让最初对买家可见的查询参数变成可用于授权的可信数据。

不要只根据 `merchantMetadata`、买家备注、电子邮箱或 URL 参数授权访问。请将订单、金额、币种、产品和关联值与你的服务端记录核对。

## 订阅载荷

订阅事件使用 `data.subscription`。重要字段包括：

| 字段                           | 含义                     |
| ---------------------------- | ---------------------- |
| `subscriptionId`、`orgId`     | Anyway 订阅和组织           |
| `status`、`provider`          | 标准生命周期状态和支付服务商         |
| `providerSubscriptionId`     | 支付服务商侧的订阅关联标识          |
| `customerId`、`customerEmail` | 可用时的客户身份               |
| `product`                    | 可选产品 `id` 和 `name`     |
| `billingInterval`            | `DAY`、`MONTH` 或 `YEAR` |
| `amountCents`、`currency`     | 最小单位金额和小写结算币种          |
| `currentPeriodEnd`           | 可用时的当前已付费周期结束时间        |
| `cancelAtPeriodEnd`          | 是否已计划在周期结束时最终取消        |
| `canceledAt`、`endedAt`       | 可用时的取消和最终结束时间          |
| `createdAt`、`updatedAt`      | RFC 3339 UTC 时间戳       |

```json theme={null}
{
  "type": "subscription.updated",
  "data": {
    "subscription": {
      "subscriptionId": "SUB_EXAMPLE",
      "orgId": "ORG_EXAMPLE",
      "providerSubscriptionId": "sub_example",
      "status": "ACTIVE",
      "customerId": "CUS_EXAMPLE",
      "customerEmail": "buyer@example.com",
      "product": {
        "id": "PRD_EXAMPLE",
        "name": "Pro Plan"
      },
      "billingInterval": "MONTH",
      "amountCents": 9900,
      "currency": "usd",
      "currentPeriodEnd": "2026-09-10T00:00:00Z",
      "cancelAtPeriodEnd": true,
      "createdAt": "2026-08-10T00:00:00Z",
      "updatedAt": "2026-08-10T08:00:00Z"
    }
  }
}
```

`merchantReference` 和 `merchantMetadata` 属于订单载荷，不是 `data.subscription` 的字段。
需要首笔结账上下文时，请使用 `subscriptionId` 查询相关订单。

## 投递行为

* 持久化加入队列后快速返回 `2xx`。
* 每次尝试的超时时间为 10 秒。
* 网络错误、`408`、`429` 和 `5xx` 会重试。
* `3xx`，以及除 `408`、`429` 之外的永久性 `4xx` 不会重试。
* 最多投递 12 次，指数退避最长一小时。
* `429` 和 `503` 的 `Retry-After` 会被采用，最长一小时。
* 投递至少一次，事件也可能乱序到达。

使用 `webhook-id` 作为投递幂等键。不要让迟到的**待处理**（`Pending`）事件把本地
**已支付**（`Paid`）订单回退，也不要让更早的订阅更新覆盖较新的生命周期状态。

<Warning>
  不要记录 Webhook 签名、API 密钥、完整付款信息、身份文件、提现账户信息或未脱敏的客户元数据。
</Warning>
