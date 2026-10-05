import type { Doc } from "./types";

const CAT = "AI & automation";

export const AI: Doc[] = [
  {
    slug: "ai-assistant",
    title: "AI assistant and 24/7 chatbot",
    category: CAT,
    minutes: 5,
    summary: "Let AI answer customers in Nepali, Romanized Nepali or English, and hand tricky chats to your team.",
    body: [
      { p: "Open **AI** in the sidebar. The **AI assistant** tab has everything the AI needs to know about your business and when it may reply." },
      { img: "ai-assistant", alt: "AI assistant settings" },
      { h: "1. Your business" },
      { p: "Write a few sentences about what you sell, where you are, delivery and payment options. Pick a tone (**Friendly**, **Professional** or **Casual**). Add detailed facts in the [Knowledge base](/docs/knowledge-base)." },
      { h: "2. Choose when the chatbot answers (Pro plan and above)" },
      { table: { head: ["Mode", "What happens"], rows: [
        ["Off", "The AI never messages customers. Your team still gets Suggest reply, Rewrite and Summaries."],
        ["Outside business hours", "Your team replies during the day; the AI answers at night and on holidays."],
        ["24/7", "The AI answers every new message straight away."],
      ] } },
      { h: "3. Handoff to your team" },
      { p: "The AI hands the conversation to a person when a customer wants to **order, pay, cancel, get a refund or exchange**, **complains**, asks for a human, or when the answer isn't in your knowledge base. It sends your handoff message (in the customer's language), leaves a yellow **internal note** with the reason, and stays quiet in that conversation." },
      { list: [
        "When an agent replies, the AI stops in that conversation (the chip shows **AI paused**).",
        "Closing the conversation, or clicking **AI paused**, lets the AI answer again next time.",
        "Messages written by the AI are purple with an **AI** badge; automations show **Auto**.",
      ] },
      { h: "4. Business hours" },
      { p: "Set your time zone and opening hours for each day. They're used by *Outside business hours* mode and by away messages. The badge shows **Open now** / **Closed now**." },
      { h: "Auto-labels" },
      { p: "Tick **Auto-label new conversations** and the AI tags each new chat as Order, Lead, Question, Complaint, Support, Feedback or Spam, so your team sees what matters first." },
      { h: "AI credits" },
      { p: "One credit = one AI action (a chatbot answer, suggestion, rewrite, summary, caption set or label). Monthly credits: Free 50, Starter 500, Pro 3,000, Business 10,000. The counter is on the right of this page and resets on the 1st." },
      { warn: "The AI only uses what you've written. It never invents prices or promises, and customer messages can't change its instructions. Always test it first in [Test the AI](/docs/test-the-ai)." },
    ],
  },
  {
    slug: "knowledge-base",
    title: "Knowledge base",
    category: CAT,
    minutes: 3,
    summary: "The facts the AI uses: products, prices, delivery, payments, returns.",
    body: [
      { steps: [
        "Go to **AI → Knowledge base** and click **Add entry** (or an example such as *Delivery charges*).",
        "Give it a clear title and write the facts the way you'd explain them to a new staff member.",
        "Click **Save**. The AI uses it immediately.",
      ] },
      { img: "knowledge", alt: "Knowledge base entries" },
      { h: "What to add first" },
      { list: [
        "Delivery charges and time (inside / outside the Valley, free-delivery limit).",
        "Payment options (COD, Khalti, eSewa, bank).",
        "Exchange and return policy.",
        "Size guide, shop address and opening hours.",
        "Your best-selling products with prices, sizes and colours.",
      ] },
      { tip: "Your **saved replies** (Settings → Saved replies) are also used by the AI, so there's no need to type things twice." },
    ],
  },
  {
    slug: "automations",
    title: "Automations: keyword, welcome and away replies",
    category: CAT,
    minutes: 4,
    summary: "Instant replies without AI: rules that run on every new message.",
    body: [
      { p: "Go to **AI → Automations**. Start from a template or click **New**. Automations are included from the Starter plan." },
      { img: "automations", alt: "Automation templates and rule list" },
      { table: { head: ["Automation", "When it runs"], rows: [
        ["Keyword reply", "A message contains a keyword like *price*, *kati*, *rate*. Can also add a tag or assign the chat."],
        ["Welcome message", "The first message from a new contact."],
        ["Away message", "Outside business hours (max once every 12 hours per customer; skipped when the AI chatbot answers)."],
        ["Comment → DM", "A comment on your Facebook/Instagram post. See [Comment to DM](/docs/comment-to-dm)."],
      ] } },
      { list: [
        "Use `{name}` in the reply for the customer's first name.",
        "Tick **Let AI write the answer** to answer from your knowledge base in the customer's language (1 credit each). Your written text is the fallback.",
        "Pick a channel or **All channels**.",
        "Switch rules on/off with the toggle. The list shows how many times each rule ran, and the last error if a platform refused a message.",
      ] },
      { tip: "Order of checks for each message: welcome → keyword → AI chatbot → away message. If a keyword rule answers, the chatbot doesn't also reply." },
      { p: "Customers who reply **STOP** are unsubscribed from broadcasts and get a confirmation; **START** subscribes them again." },
    ],
  },
  {
    slug: "comment-to-dm",
    title: "Comment → DM (auto-reply to post comments)",
    category: CAT,
    minutes: 3,
    summary: "Someone comments \"price?\" on your post and instantly gets the details in their inbox.",
    body: [
      { steps: [
        "Connect your Facebook Page as a **Messenger** channel (and/or Instagram). See [Messenger](/docs/messenger).",
        "Go to **AI → Automations** and click the **Price comments → DM** template.",
        "Choose the Page, the keywords (leave empty to answer every comment) and, optionally, one post ID.",
        "Write the private message, for example *Namaste {name}! Price is Rs 1,800. Reply here to order!*. Tick **Let AI write the answer** for personalised answers.",
        "Optional: a **public reply** under the comment, e.g. *Sent you a DM, {name}! 📩*",
        "Click **Create automation**.",
      ] },
      { img: "automation-comment-dm", alt: "Comment to DM automation editor" },
      { list: [
        "Meta allows **one private reply per comment**, within 7 days.",
        "Comments are picked up instantly by webhook (Page `feed` and Instagram `comments` fields) and checked every worker cycle as a backup.",
        "Only comments made after you create the rule are answered. Old commenters never get messages.",
        "Needs the `pages_manage_engagement` permission for public replies and `instagram_manage_comments` for Instagram.",
      ] },
    ],
  },
  {
    slug: "test-the-ai",
    title: "Test the AI before turning it on",
    category: CAT,
    minutes: 2,
    summary: "See exactly what the AI would answer. Nothing is sent to anyone.",
    body: [
      { steps: [
        "Go to **AI → Test the AI**.",
        "Click an example question or type one the way your customers write (Nepali, Romanized Nepali, English…).",
        "Check the answer, and whether the AI **answers** or **hands over to your team** (with the reason).",
        "Missing or wrong facts? Improve your knowledge base and test again.",
      ] },
      { img: "test-ai", alt: "Testing the AI with two questions" },
      { p: "Each test uses 1 AI credit." },
    ],
  },
];
