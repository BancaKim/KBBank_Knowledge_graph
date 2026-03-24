export interface GraphNode {
  id: string;
  label: string;
  type:
    | "product"
    | "category"
    | "parentcategory"
    | "feature"
    | "interestrate"
    | "term"
    | "channel"
    | "eligibilitycondition"
    | "repaymentmethod"
    | "taxbenefit"
    | "depositprotection"
    | "preferentialrate"
    | "fee"
    | "producttype";
  group: number;
  data: Record<string, unknown>;
  // D3 simulation properties
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  value: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  metadata: {
    node_types: string[];
    edge_types: string[];
    stats: {
      total_nodes: number;
      total_edges: number;
    };
  };
}

export interface Product {
  id: string;
  name: string;
  product_type: string;
  description: string;
  amount_max_raw: string;
  amount_max_won: number | null;
  eligibility_summary: string;
  page_url: string;
  category?: string;
  rate_min?: number | null;
  rate_max?: number | null;
}

export interface Category {
  id: string;
  name: string;
  name_en: string;
  product_count: number;
}

export interface SearchResult {
  products: Product[];
  total: number;
}

export const NODE_COLORS: Record<string, string> = {
  product: "#4A90D9",
  category: "#F5A623",
  parentcategory: "#E65100",
  feature: "#7ED321",
  interestrate: "#D0021B",
  term: "#9B59B6",
  channel: "#1ABC9C",
  eligibilitycondition: "#95A5A6",
  repaymentmethod: "#E67E22",
  taxbenefit: "#27AE60",
  depositprotection: "#2980B9",
  preferentialrate: "#E74C3C",
  fee: "#8E44AD",
  producttype: "#16A085",
};

export const NODE_GROUPS: Record<string, number> = {
  product: 0,
  category: 1,
  parentcategory: 2,
  feature: 3,
  interestrate: 4,
  term: 5,
  channel: 6,
  eligibilitycondition: 7,
  repaymentmethod: 8,
  taxbenefit: 9,
  depositprotection: 10,
  preferentialrate: 11,
  fee: 12,
  producttype: 13,
};
