/** Help-center content. Text supports **bold**, `code` and [links](/path). */
export type Block =
  | { p: string }
  | { h: string }
  | { steps: string[] }
  | { list: string[] }
  | { img: string; alt: string; caption?: string; narrow?: boolean }
  | { tip: string }
  | { warn: string }
  | { code: string; lang?: string }
  | { table: { head: string[]; rows: string[][] } };

export type Doc = {
  slug: string;
  title: string;
  category: string;
  summary: string;
  minutes?: number;
  body: Block[];
};
