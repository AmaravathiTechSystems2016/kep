===============================
Performance Appraisal (mj_appraisal)
===============================

This module provides a structured Performance Appraisal system for employees in Odoo. 
It allows administrators to assign multiple appraisers, distribute evaluation weights, 
and manage a complete appraisal workflow with controlled finalization.

====================================
Features
====================================

- Create employee performance appraisals
- Assign multiple appraisers per appraisal
- Distribute evaluation weight (total = 100)
- Appraisers can define evaluation criteria and assign scores
- Smart button to view all assigned appraisers
- Validation of total allocated points
- Final confirmation locks the appraisal (read-only)

====================================
Workflow
====================================

1. Create Appraisal
-------------------
- Go to Employee module
- Open *Performance Appraisal*
- Click *New*
- Fill in:
  - Appraisal Name
  - Evaluation Period
  - Employee
  - Appraisal Date

2. Assign Appraisers
--------------------
- Add one or more appraisers
- Allocate points to each appraiser

**Important:**
Total allocated points must equal **100**.

3. Review Appraisers
--------------------
- Click on the *Appraisers Count* smart button
- View all assigned appraisers

4. Appraiser Evaluation
-----------------------
- Each appraiser accesses their assigned line
- Add evaluation criteria and scores
- Ensure total scores align with allocated weightage


5. Final Confirmation
---------------------
- Admin reviews all evaluations
- Click *Confirm* to finalize

After confirmation:
- Appraisal becomes read-only
- No further modifications are allowed

====================================
Security
====================================

- Viewer: Can view appraisal data
- Manager: Full control over appraisal process
- Portal users (optional): Can access their assigned appraisals (on demand)

====================================
Technical Notes
====================================

- Model: ``performance.appraiser``
- Uses Odoo mail tracking (chatter enabled)
- Supports multi-user evaluation workflow
- Includes portal integration capability (on demand)

====================================
Installation
====================================

1. Place the module in your custom addons directory
2. Update apps list
3. Install *Performance Appraisal (mj_appraisal)*

====================================
Author
====================================

Developed by Musleh Uddin Juned

====================================
License
====================================

LGPL-3