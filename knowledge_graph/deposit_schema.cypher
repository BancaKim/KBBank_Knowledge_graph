// =========================================================================
// Neo4j schema initialization for banking_bot knowledge graph
// =========================================================================

// --- Uniqueness constraints ------------------------------------------------
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT category_id IF NOT EXISTS FOR (c:Category) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT parentcategory_id IF NOT EXISTS FOR (pc:ParentCategory) REQUIRE pc.id IS UNIQUE;
CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (f:Feature) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT interestrate_id IF NOT EXISTS FOR (r:InterestRate) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT term_id IF NOT EXISTS FOR (t:Term) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT channel_id IF NOT EXISTS FOR (ch:Channel) REQUIRE ch.id IS UNIQUE;
CREATE CONSTRAINT eligibilitycondition_id IF NOT EXISTS FOR (e:EligibilityCondition) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT repaymentmethod_id IF NOT EXISTS FOR (rm:RepaymentMethod) REQUIRE rm.id IS UNIQUE;
CREATE CONSTRAINT taxbenefit_id IF NOT EXISTS FOR (tb:TaxBenefit) REQUIRE tb.id IS UNIQUE;
CREATE CONSTRAINT depositprotection_id IF NOT EXISTS FOR (dp:DepositProtection) REQUIRE dp.id IS UNIQUE;
CREATE CONSTRAINT preferentialrate_id IF NOT EXISTS FOR (pr:PreferentialRate) REQUIRE pr.id IS UNIQUE;
CREATE CONSTRAINT fee_id IF NOT EXISTS FOR (f:Fee) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT producttype_id IF NOT EXISTS FOR (pt:ProductType) REQUIRE pt.id IS UNIQUE;

// --- Full-text search indexes (CJK analyzer for Korean) --------------------
CREATE FULLTEXT INDEX product_search IF NOT EXISTS FOR (p:Product) ON EACH [p.name, p.description] OPTIONS { indexConfig: { `fulltext.analyzer`: 'cjk' } };
CREATE FULLTEXT INDEX category_search IF NOT EXISTS FOR (c:Category) ON EACH [c.name] OPTIONS { indexConfig: { `fulltext.analyzer`: 'cjk' } };
CREATE FULLTEXT INDEX feature_search IF NOT EXISTS FOR (f:Feature) ON EACH [f.name, f.description] OPTIONS { indexConfig: { `fulltext.analyzer`: 'cjk' } };

// --- Lookup indexes for common queries -------------------------------------
CREATE INDEX product_product_type IF NOT EXISTS FOR (p:Product) ON (p.product_type);
