// Loan-specific Neo4j schema constraints and indexes
// Separate from deposit schema — coexists in same Aura DB

CREATE CONSTRAINT loan_product_id IF NOT EXISTS FOR (lp:LoanProduct) REQUIRE lp.id IS UNIQUE
CREATE CONSTRAINT loan_category_id IF NOT EXISTS FOR (lc:LoanCategory) REQUIRE lc.id IS UNIQUE
CREATE CONSTRAINT loan_rate_id IF NOT EXISTS FOR (lr:LoanRate) REQUIRE lr.id IS UNIQUE
CREATE CONSTRAINT loan_term_id IF NOT EXISTS FOR (lt:LoanTerm) REQUIRE lt.id IS UNIQUE
CREATE CONSTRAINT loan_elig_id IF NOT EXISTS FOR (le:LoanEligibility) REQUIRE le.id IS UNIQUE
CREATE CONSTRAINT repayment_method_id IF NOT EXISTS FOR (rm:RepaymentMethod) REQUIRE rm.id IS UNIQUE
CREATE CONSTRAINT loan_fee_id IF NOT EXISTS FOR (lf:LoanFee) REQUIRE lf.id IS UNIQUE
CREATE CONSTRAINT loan_pref_rate_id IF NOT EXISTS FOR (lpr:LoanPreferentialRate) REQUIRE lpr.id IS UNIQUE
CREATE CONSTRAINT collateral_id IF NOT EXISTS FOR (c:Collateral) REQUIRE c.id IS UNIQUE

CREATE INDEX loan_product_type IF NOT EXISTS FOR (lp:LoanProduct) ON (lp.loan_type)
CREATE INDEX loan_category_name IF NOT EXISTS FOR (lc:LoanCategory) ON (lc.name)
