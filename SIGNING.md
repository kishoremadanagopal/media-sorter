# Signing Media Sorter with your name (Microsoft Artifact Signing)

When it's set up, every GitHub build signs **MediaSorter.exe**, **Uninstall.exe** and the **Setup.exe**.
Windows then shows **"Verified publisher: Kishore Madanagopal"** instead of "Unknown publisher".

- **Cost:** Basic plan, $9.99 / month (up to 5,000 signatures; one build uses 3).
- **Who can use it as an individual:** people in the USA or Canada. ✔ You're in San Jose, CA.
- **Time:** about 1 hour of clicking, plus 1–20 business days for Microsoft to check your ID.
- Everything below is done in a web browser. No command window.

---

## Part 1 — Azure account and identity check (one time)

1. **Create an Azure account** at portal.azure.com (sign in with your Microsoft account).
   When asked, choose a **pay-as-you-go** subscription with account type **Individual**.
   ⚠ Your **billing name and address must exactly match your government ID** (driver's license or passport).
2. **Turn on the signing service:** search **Subscriptions** → your subscription → **Resource providers**
   → search `Microsoft.CodeSigning` → **Register**.
3. **Create the signing account:** search **Artifact Signing accounts** → **Create**.
   - Resource group: *Create new* → `media-sorter-signing`
   - Account name: for example `kishoresigning` (letters and numbers only)
   - Region: **West US 2** (closest to you)
   - Pricing: **Basic**
   → **Review + create** → **Create**.
4. **Give yourself permission to verify:** open the new account → **Access control (IAM)** → **Add role assignment**
   → **Artifact Signing Identity Verifier** → add **yourself** → **Review + assign**.
5. **Verify your identity:** in the account → **Identity validations** → **New identity** → **Individual**
   → **Public** → fill in your details exactly as on your ID → **Create**.
   Microsoft emails you a link to finish the check (ID photo + selfie). Wait for the **Completed** email.
6. **Create the certificate profile:** in the account → **Certificate profiles** → **Create** → **Public Trust**
   - Name: `mediasorter`
   - Verified CN and O: pick your completed identity (this is where *Kishore Madanagopal* comes from)
   → **Create**.

## Part 2 — Let GitHub sign for you (one time)

This uses a secure, password-free link between GitHub and Azure.

7. **Register an app for GitHub:** search **App registrations** → **New registration**
   → name `media-sorter-github` → **Register**. On its overview page, copy:
   **Application (client) ID** and **Directory (tenant) ID**.
8. **Trust your GitHub repository:** in that app → **Certificates & secrets** → **Federated credentials**
   → **Add credential** → scenario **GitHub Actions deploying Azure resources**
   - Organization: `kishoremadanagopal` · Repository: `media-sorter` (your repo name)
   - Entity type: **Environment** · Environment name: `signing` → name it `github-signing` → **Add**.
   (The build always runs in a GitHub environment called `signing`, so this one setting covers normal
   builds and release builds. GitHub creates the environment by itself on the first run.)
9. **Allow it to sign:** back in your Artifact Signing account → **Access control (IAM)** → **Add role assignment**
   → **Artifact Signing Certificate Profile Signer** → **Members: + Select members** → search
   `media-sorter-github` → **Review + assign**.
10. **Copy your Subscription ID:** search **Subscriptions** → copy the **Subscription ID**.

## Part 3 — Tell GitHub the details (one time)

11. In your GitHub repository → **Settings** → **Secrets and variables** → **Actions**.
12. **Secrets** tab → **New repository secret**, three times:

    | Name | Value |
    |---|---|
    | `AZURE_CLIENT_ID` | Application (client) ID from step 7 |
    | `AZURE_TENANT_ID` | Directory (tenant) ID from step 7 |
    | `AZURE_SUBSCRIPTION_ID` | Subscription ID from step 10 |

13. **Variables** tab → **New repository variable**, three times:

    | Name | Value |
    |---|---|
    | `ARTIFACT_SIGNING_ENDPOINT` | `https://wus2.codesigning.azure.net` (for West US 2) |
    | `ARTIFACT_SIGNING_ACCOUNT` | your account name from step 3, e.g. `kishoresigning` |
    | `ARTIFACT_SIGNING_PROFILE` | `mediasorter` |

That's it. Run **Actions → Build Windows installer → Run workflow**. The step **"Show who signed the files"**
lists all three files as `Valid` with your name. Signing switches on automatically once
`ARTIFACT_SIGNING_ACCOUNT` exists; before that, builds still work, just unsigned.

---

## Good to know

- **SmartScreen may still warn at first.** Since 2024, no certificate gives instant trust; Windows builds
  reputation for your name as people install the app safely. Signing makes the warning go away sooner and
  shows your name. Keep signing with the same profile every time so trust carries over between versions.
- **Extra safety (optional):** GitHub → Settings → Environments → `signing` → **Required reviewers** → add
  yourself. Then every signed build waits for your OK before using your name.
- **Costs:** you pay $9.99 each month while the signing account exists. Deleting the account stops billing;
  already-signed files stay valid (they're time-stamped).
- If your region isn't West US 2, use the matching endpoint (e.g. West US = `https://wus.codesigning.azure.net`).

Sources: Microsoft Artifact Signing quickstart (learn.microsoft.com/azure/artifact-signing/quickstart);
Artifact Signing GitHub Action README and OIDC guide (github.com/azure/artifact-signing-action);
DevClass, 14 Jan 2026 (pricing and eligibility).
