/** Nepali translations, merged from one file per area. Keys are the exact English text shown in the app. */
import account from "./account";
import affiliate from "./affiliate";
import commerce from "./commerce";
import common from "./common";
import growth from "./growth";
import inbox from "./inbox";
import knowledge from "./knowledge";
import mobile from "./mobile";
import publicPages from "./public";
import publisher from "./publisher";
import sales from "./sales";
import workspace from "./workspace";

const NE: Record<string, string> = {
  ...publisher, ...sales, ...knowledge, ...mobile, ...affiliate, ...publicPages, ...workspace, ...account, ...growth, ...commerce, ...inbox,
  ...common,  // shared words win if an area file defined them too
};

export default NE;
