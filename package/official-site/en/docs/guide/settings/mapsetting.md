# Map Settings Guide

TrailSnap uses map services to display the geographical distribution of photos (Footprint Map). In order to use the map function normally, you need to apply for and configure the API Key of the map service yourself.

## Why configure an API Key?

Map service providers (such as Tianditu, Amap, Baidu) usually require developers to apply for an independent API Key (or Token) to call their services. Configuring your own Key has the following benefits:
1. **Stability Guarantee**: Have an independent daily call quota to avoid map loading failure due to shared Key reaching the limit.
2. **Compliance and Security**: Comply with the terms of use of the map service provider, and the Key is managed by yourself, which is more secure.

---

## 1. Tianditu (Recommended)

[Tianditu](https://www.tianditu.gov.cn/) is a national geographic information public service platform with authoritative data and full coverage. It provides a relatively generous free quota for individual developers and is the **default and recommended** map service provider for TrailSnap.

### Steps to Get API Key (Tk)

1. **Register Account**
   Visit the [Tianditu Official Website](https://www.tianditu.gov.cn/), click "Register" in the upper right corner, and complete personal account registration. If you already have an account, [log in](https://sso.tianditu.gov.cn/login) directly.

2. **Enter Console**
   After logging in, click "Development Resources" at the top of the page, select "Console", or visit the [Tianditu Console](http://lbs.tianditu.gov.cn/server/kz.html) directly.

3. **Apply to be a Developer**
   If it is your first time using it, you may need to click "Apply to become an individual developer" and complete simple real-name authentication.

4. **Create Application**
   - Click **"Application Management"** in the left menu bar.
   - Click the **"Create New Application"** button.
   - Fill in application information:
     - **Application Name**: Fill in `TrailSnap` or any name you like.
     - **Industry Category**: Select according to the actual situation (e.g., "Life Service").
     - **Application Type**: **Must select "Browser Side"** (because TrailSnap loads the map directly on the browser frontend).
     - **IP Whitelist/Domain Whitelist**:
       - If you use it locally (`localhost`), you can fill in `*` (meaning no restriction).
       - If you use TrailSnap Desktop, leave it unrestricted; the desktop WebView's internal origin is not suitable for a fixed domain whitelist.
       - If you deploy on the public network, it is recommended to fill in your domain name or IP address to improve security.

5. **Get Key**
   After successful creation, you will see the application just created in the application list. Copy the string of characters corresponding to the **Key** column (usually called `tk`).

6. **Fill in Settings**
   Return to the TrailSnap system:
   - Go to **Settings** -> **Basic Settings**.
   - Find the **Map Configuration** area.
   - Ensure the map provider is selected as **Tianditu**.
   - Paste the copied Key into the **API Key** input box.
   - Click Save.

7. **Get Multiple Keys and Configure**
   - Tianditu allows you to create multiple Keys for different applications or scenarios, and each Key has an independent call quota.
   - To prevent excessive calls, you can configure multiple Keys in TrailSnap, and the system will randomly select one to load the map.
   - This is very useful when you need to use different Keys in different environments (such as local development, test environment, production environment).

---

## 2. Amap (Gaode Map)

> **Note**: TrailSnap currently mainly supports Tianditu. Support for Amap is under development, and configuration may not take effect temporarily or only some functions may be available.

### Steps to Get API Key

1. **Register Developer**
   Visit the [Amap Open Platform](https://console.amap.com/dev/index), register an account and complete developer authentication (individual developer is sufficient).

2. **Create Application**
   - Enter **Application Management** -> **My Applications**.
   - Click **Create New Application**, enter name (e.g., `TrailSnap`) and type (e.g., `Tool`).

3. **Add Key**
   - Under the application just created, click **Add Key**.
   - **Service Platform**: Select **Web Side (JSAPI)**.
   - **Domain Whitelist**: Can be left blank for local testing, please fill in the domain name for online deployment.
   - Check agree to the agreement and submit.

4. **Get Key**
   Copy the generated **Key**. Note: Amap JSAPI 2.0 may also require configuring a security key (jscode). Currently, TrailSnap does not support configuring security keys through the interface. It is recommended to prioritize using Tianditu.

---

## 3. Baidu Map

> **Note**: Support for Baidu Map is being planned.

### Steps to Get API Key (AK)

1. **Register Developer**
   Visit the [Baidu Map Open Platform](https://lbsyun.baidu.com/apiconsole/center), register and authenticate.

2. **Create Application**
   - Enter **Application Management** -> **My Applications**.
   - Click **Create Application**.

3. **Configure Application**
   - **Application Type**: Select **Browser Side**.
   - **Referer Whitelist**: Fill in `*` (local testing) or your domain name.
   - **Enable Services**: Default select all.

4. **Get AK**
   After submission, the **Access Application (AK)** in the list is the API Key.

---

## 4. Offline Map Data

TrailSnap supports offline reverse geocoding. Even without an internet connection, it can resolve the city and region based on the GPS coordinates of photos. This feature relies on offline city data files.

### Feature Description

You can find the **Offline Map Data** management area under **Settings** -> **Basic Settings** -> **Map Configuration**.

### Download Country Data
1. In the **Download Country Data** area, select the country you need (e.g., "China") from the dropdown menu.
2. Click the **Download** button.
3. The system will automatically download and process the city data for that country in the background. Once completed, the country's data will appear in the **Downloaded Data** list below.

### Upload Custom Data
If you cannot download directly through the system, or have custom city data files, you can manually upload them using this feature.
1. Prepare a city data file in CSV format. The file must include the following header fields:
   - `longitude`: Longitude
   - `latitude`: Latitude
   - `country`: Country Code (e.g., CN, US)
   - `admin_1`: Admin Level 1 (e.g., Province/State)
   - `admin_2`: Admin Level 2 (e.g., City)
   - `admin_3`: Admin Level 3 (e.g., District/County)
   - `admin_4`: Admin Level 4 (Optional)
2. Click the **Click to Upload CSV File** button and select your file.
3. After successful upload, the data will take effect immediately and appear in the list.

### Manage Downloaded Data
In the **Downloaded Data** list, you can:
- View all currently installed country/region data.
- Click the **Download Icon** next to the filename to download the CSV data file from the server to your local computer for backup or inspection.

---

## FAQ

**Q: Map loads blank or grid?**
A: 
1. Please check if the API Key is copied correctly, be careful not to include spaces.
2. Confirm if the **Application Type** selected when applying for the Key is correct (Tianditu must be **Browser Side**).
3. If a whitelist is set, please confirm whether the current access address (such as `localhost` or `127.0.0.1`) is in the whitelist.
4. For TrailSnap Desktop, remove the domain restriction and validate the Key again from Settings.

**Q: What if the Tianditu quota is not enough?**
A: The free quota for individual developers is usually sufficient for daily browsing needs of personal albums. If it really exceeds the limit, you can consider registering multiple accounts or upgrading to enterprise certification.

**Q: Offline map data download failed?**
A: It may be due to network connection issues preventing connection to the data source (GeoNames). You can try again later, or manually download the data and import it using the "Upload Custom Data" feature.
