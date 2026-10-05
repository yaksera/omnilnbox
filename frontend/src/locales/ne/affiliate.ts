/** Affiliate program: the affiliate dashboard, promo codes on sign-up and Billing, and payouts. */
const dict: Record<string, string> = {
  // entry points
  "Refer & earn": "रेफर गरेर कमाउनुहोस्",
  "Promo code (optional)": "प्रोमो कोड (ऐच्छिक)",
  "Referred by {name}": "{name} ले रेफर गर्नुभएको",
  "Have a promo code?": "प्रोमो कोड छ?",
  "Add it before your first payment.": "पहिलो भुक्तानी गर्नुअघि थप्नुहोस्।",
  "Apply": "लागू गर्नुहोस्",
  "Couldn't apply the code": "कोड लागू गर्न सकिएन",
  "Promo code {code} is applied to this workspace.": "यो वर्कस्पेसमा प्रोमो कोड {code} लागू भएको छ।",
  "Refer businesses, earn every month": "व्यवसायहरू रेफर गर्नुहोस्, हरेक महिना कमाउनुहोस्",
  "Share your link or promo code and earn a commission on every payment they make, for as long as they stay subscribed.":
    "आफ्नो लिङ्क वा प्रोमो कोड सेयर गर्नुहोस् र उनीहरूले सब्सक्राइब गरिरहेसम्म हरेक भुक्तानीमा कमिसन कमाउनुहोस्।",
  // errors from the server
  "This promo code isn't valid.": "यो प्रोमो कोड मान्य छैन।",
  "A promo code has already been applied to this workspace.": "यो वर्कस्पेसमा पहिले नै प्रोमो कोड लागू भइसकेको छ।",
  "You can't use your own promo code.": "तपाईं आफ्नै प्रोमो कोड प्रयोग गर्न सक्नुहुन्न।",
  "Promo codes can only be added before the first payment.": "प्रोमो कोड पहिलो भुक्तानीअघि मात्र थप्न सकिन्छ।",
  "Add your eSewa, Khalti or bank details first.": "पहिले आफ्नो eSewa, Khalti वा बैंक विवरण थप्नुहोस्।",
  "You already have a payout request being processed.": "तपाईंको एउटा भुक्तानी अनुरोध प्रक्रियामा छ।",

  // dashboard
  "Affiliate program": "एफिलिएट कार्यक्रम",
  "Earn {rate} of every payment from businesses you refer, every month, for as long as they stay subscribed.":
    "तपाईंले रेफर गरेका व्यवसायहरूले सब्सक्राइब गरिरहेसम्म, उनीहरूको हरेक भुक्तानीको {rate} हरेक महिना कमाउनुहोस्।",
  "Share your link or code": "आफ्नो लिङ्क वा कोड सेयर गर्नुहोस्",
  "Post it on Facebook, TikTok, YouTube or send it to businesses you know.":
    "Facebook, TikTok, YouTube मा पोस्ट गर्नुहोस् वा चिनेका व्यवसायलाई पठाउनुहोस्।",
  "They subscribe": "उनीहरू सब्सक्राइब गर्छन्",
  "They sign up through your link, or enter your promo code on the sign-up or Billing page.":
    "उनीहरू तपाईंको लिङ्कबाट साइन अप गर्छन्, वा साइन अप वा बिलिङ पेजमा तपाईंको प्रोमो कोड हाल्छन्।",
  "You earn every month": "तपाईं हरेक महिना कमाउनुहुन्छ",
  "Get {rate} of each payment they make, as long as they stay subscribed. Paid to eSewa, Khalti or your bank.":
    "उनीहरूले सब्सक्राइब गरिरहेसम्म हरेक भुक्तानीको {rate} पाउनुहोस्। eSewa, Khalti वा बैंकमा भुक्तानी।",
  "Apply to become an affiliate": "एफिलिएट बन्न आवेदन दिनुहोस्",
  "We review applications within 1-2 days. Commissions become payable {days} days after each payment, and you can withdraw once you have {min}.":
    "हामी १-२ दिनभित्र आवेदन हेर्छौं। हरेक भुक्तानीको {days} दिनपछि कमिसन निकाल्न मिल्छ, र {min} पुगेपछि झिक्न सक्नुहुन्छ।",
  "Your promo code": "तपाईंको प्रोमो कोड",
  "4-20 letters or numbers. It's also your link: {link}": "४-२० अक्षर वा अंक। यही तपाईंको लिङ्क पनि हो: {link}",
  "How should we pay you?": "हामीले तपाईंलाई कसरी भुक्तानी गर्ने?",
  "Bank transfer": "बैंक ट्रान्सफर",
  "Account holder name": "खातावालाको नाम",
  "eSewa ID (mobile number)": "eSewa ID (मोबाइल नम्बर)",
  "Khalti ID (mobile number)": "Khalti ID (मोबाइल नम्बर)",
  "Account number": "खाता नम्बर",
  "Bank and branch": "बैंक र शाखा",
  "How will you promote OmniInbox? (optional)": "तपाईं OmniInbox को प्रचार कसरी गर्नुहुन्छ? (ऐच्छिक)",
  "e.g. my YouTube channel for online sellers, a Facebook group, my clients…":
    "जस्तै: अनलाइन बिक्रेताका लागि मेरो YouTube च्यानल, Facebook समूह, मेरा ग्राहकहरू…",
  "Apply now": "अहिले आवेदन दिनुहोस्",
  "Application sent. We'll email you once it's approved.": "आवेदन पठाइयो। स्वीकृत भएपछि हामी इमेल गर्नेछौं।",
  "Your application is being reviewed": "तपाईंको आवेदन जाँच हुँदैछ",
  "Your code {code} will start working once we approve it. We'll email you.":
    "हामीले स्वीकृत गरेपछि तपाईंको कोड {code} चल्न थाल्छ। हामी इमेल गर्नेछौं।",
  "Your application wasn't approved": "तपाईंको आवेदन स्वीकृत भएन",
  "Your affiliate account is suspended": "तपाईंको एफिलिएट खाता निलम्बित छ",
  "Questions? Contact OmniInbox support.": "प्रश्न छ? OmniInbox सपोर्टलाई सम्पर्क गर्नुहोस्।",
  "You're an approved affiliate · {rate} recurring": "तपाईं स्वीकृत एफिलिएट हुनुहुन्छ · {rate} हरेक भुक्तानीमा",
  "Your tracking link": "तपाईंको ट्र्याकिङ लिङ्क",
  "Anyone who opens your link is remembered for 60 days. They can also type your code when signing up or on the Billing page before their first payment.":
    "तपाईंको लिङ्क खोल्ने जो कोही ६० दिनसम्म सम्झिइन्छ। उनीहरूले साइन अप गर्दा वा पहिलो भुक्तानीअघि बिलिङ पेजमा पनि तपाईंको कोड हाल्न सक्छन्।",
  "Link clicks": "लिङ्क क्लिक",
  "{n} in the last 30 days": "पछिल्लो ३० दिनमा {n}",
  "Sign-ups": "साइन अप",
  "Paying customers": "भुक्तानी गर्ने ग्राहक",
  "Total earned": "जम्मा कमाइ",
  "Balance": "ब्यालेन्स",
  "Available to withdraw": "झिक्न मिल्ने",
  "Holding": "होल्डमा",
  "Payout requested": "भुक्तानी अनुरोध गरिएको",
  "Paid to you": "तपाईंलाई भुक्तानी भएको",
  "New commissions are held for {days} days in case of refunds, then become available.":
    "रिफन्ड हुन सक्ने भएकाले नयाँ कमिसन {days} दिन होल्डमा रहन्छ, त्यसपछि झिक्न मिल्छ।",
  "Withdraw {amount}": "{amount} झिक्नुहोस्",
  "Minimum withdrawal: {min}": "न्यूनतम झिक्न मिल्ने रकम: {min}",
  "Payout requested. We'll send it within a few working days.": "भुक्तानी अनुरोध गरियो। केही कार्य दिनभित्र पठाउनेछौं।",
  "Payout details": "भुक्तानी विवरण",
  "Payout details saved.": "भुक्तानी विवरण सेभ भयो।",
  "Commissions": "कमिसनहरू",
  "No commissions yet. They appear here when someone you referred pays.":
    "अहिलेसम्म कमिसन छैन। तपाईंले रेफर गरेको कसैले भुक्तानी गरेपछि यहाँ देखिन्छ।",
  "{rate} of {amount} · {date}": "{amount} को {rate} · {date}",
  "available {date}": "{date} देखि झिक्न मिल्ने",
  "Available": "झिक्न मिल्ने",
  "Void": "रद्द",
  "Businesses you referred": "तपाईंले रेफर गरेका व्यवसाय",
  "No sign-ups yet. Share your link to get started.": "अहिलेसम्म साइन अप छैन। सुरु गर्न आफ्नो लिङ्क सेयर गर्नुहोस्।",
  "via link": "लिङ्कबाट",
  "via code": "कोडबाट",
  "Subscribed": "सब्सक्राइब गरेको",
  "Cancelled": "रद्द गरेको",
  "Free plan": "निःशुल्क प्लान",
  "Payouts": "भुक्तानीहरू",
  "Requested {date}": "{date} मा अनुरोध गरिएको",
  "Txn {ref}": "कारोबार {ref}",
  "Processing": "प्रक्रियामा",
};

export default dict;
