# POL-004: Information Security and Data Protection Policy

**Owner:** Security Team | **Effective:** January 1, 2026 | **Applies to:** All employees, contractors, and anyone who accesses Northwind systems

## 1. Purpose

This policy protects Northwind's information, our customers' data, and the personal data of our people. Everyone who uses Northwind systems is responsible for following it. Security questions can be sent to the Security team at security@northwind.example.

## 2. Data Classification

Northwind classifies information into four levels:

- **Public:** approved for release, such as published blog posts.
- **Internal:** general business information not meant for outsiders, such as org charts and non-sensitive policies.
- **Confidential:** customer data, source code, unreleased product plans, and non-public financial results.
- **Restricted:** the most sensitive data, including employee personal records, payroll and banking data, payment data, authentication secrets, and regulated health data.

Each employee has a **data access level** recorded in the HR system that reflects the highest classification they routinely use: Standard, Confidential, or Restricted. Employees in the Finance, Security, and People teams normally hold Restricted access. Employees in Engineering, Data Science, and Customer Support normally hold Confidential access. Employees in other teams, such as Design, normally hold Standard access.

## 3. Device and Network Requirements

All work devices must:

1. Use full-disk encryption and be enrolled in Northwind's device management system (MDM);
2. Lock automatically after 5 minutes of inactivity;
3. Run the approved endpoint protection software and receive updates within 7 days of release; and
4. Use the corporate VPN whenever the user accesses Confidential or Restricted data from outside a Northwind office.

Public Wi-Fi networks, such as those in airports, hotels, and cafes, may be used only with the VPN turned on. Employees must not connect work devices to unknown USB devices or charging stations.

## 4. Approved Countries for Confidential and Restricted Data Access

To manage legal and data-protection risk, employees with Confidential or Restricted data access may sign in to Northwind systems only from the following approved countries: United States, Canada, United Kingdom, Ireland, Germany, France, Netherlands, Spain, Portugal, Australia, Singapore, and Pakistan.

Employees with Standard access may sign in from any country that is not on the sanctioned list in POL-003, Section 5. Access attempts from non-approved countries by Confidential and Restricted users are blocked automatically and are logged. Exceptions require written approval from the Chief Information Security Officer (CISO) and cannot be granted for sanctioned countries.

## 5. Security Requirements for Remote and International Work

Employees who work from another country under POL-003 must:

- complete a **security review** before travel if they hold Confidential or Restricted access. The review confirms that the destination is on the approved list, that the device is up to date, and that the employee understands the travel guidance;
- use only a Northwind-issued laptop. Personal devices must never be used for Restricted data;
- keep the VPN on at all times while working;
- avoid working in shared public spaces where a screen can be seen by others; and
- consider requesting a loaner travel laptop from IT for high-risk destinations (see POL-010).

## 6. Multi-Factor Authentication and Passwords

Multi-factor authentication (MFA) is mandatory for all Northwind accounts. Passwords must be at least 14 characters and be stored only in the company-approved password manager. Passwords and MFA codes must never be shared, including with managers or IT staff.

## 7. Incident Reporting

Any suspected security incident must be reported to the Security team **within 1 hour of discovery**. This includes phishing that was clicked, malware warnings, accidental disclosure of data, and lost or stolen devices. Employees should not try to investigate or fix the problem themselves. Reporting quickly and in good faith is never grounds for discipline. Lost or stolen equipment must also be reported to the IT Service Desk within 24 hours so asset records can be updated (see POL-010).

## 8. Acceptable Use and Artificial Intelligence Tools

Work devices and accounts are for business use with limited personal use that does not create risk. Employees may use only company-approved AI tools with Northwind data. Confidential and Restricted data must never be entered into AI tools or services that Northwind has not approved. Output from AI tools must be reviewed by a person before it is used with customers or in decisions about people.

## 9. Handling Personal Data

Employee and customer personal data must be accessed only when there is a business need, and must not be copied to personal email, personal cloud storage, or removable drives. Printouts of Restricted data must be shredded.

## 10. Consequences

Violations of this policy can lead to loss of access and corrective action under POL-008, up to and including termination. Serious violations may also have legal consequences.
