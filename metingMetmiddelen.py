import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import pandas as pd
import json

aantalpieken = 0
instellingen = {
    "kanaal": "CHAN1",
    "volt_per_div": 0.05,  # 50mV per vakje
    "tijd_per_div": 50e-6,  # 50us per vakje
    "trigger_level": -0.1,  # Trigger op -80mV
    "trigger_type": "PULS",
    "trigger_condition": "NLEV",  # Negative Level / Pulse
}
sessie_data = {
    "datum": time.ctime(),
    "configuratie": instellingen,  # Hier staan nu al je kanaalinstellingen in!
    "metingen": [],
}
minuten = input("Hoe veel minuten?")
while True:
    try:
        Nmeting = float(minuten) * 60
        break
    except:
        raise Exception("Geef een geldig nummer")

# --- 1. Verbinding ---
rm = pyvisa.ResourceManager()
try:
    scope = rm.open_resource(rm.list_resources()[0])
    scope.timeout = 20000
    print(f"Verbonden met: {scope.query('*IDN?').strip()}")
except:
    print("Geen scope gevonden. Controleer de USB-kabel.")
    exit()

# --- 2. Configuratie ---
scope.write("*RST")
time.sleep(1)
scope.write(":STOP")

# Kanaalinstellingen
# --- Configuratie blok ---
# --- Uitvoeren naar de Scope ---
# BELANGRIJK nakijken of dit zo werkt.
scope.write(f":{instellingen['kanaal']}:DISP ON")
scope.write(f":{instellingen['kanaal']}:SCAL {instellingen['volt_per_div']}")
scope.write(f":TIM:SCAL {instellingen['tijd_per_div']}")

# Trigger instellingen
scope.write(f":TRIG:MODE PULS")
scope.write(f":TRIG:PULS:SOUR {instellingen['kanaal']}")
scope.write(f":TRIG:PULS:WHEN {instellingen['trigger_condition']}")
scope.write(f":TRIG:PULS:LEV -0.1")
scope.write(":TRIG:SWEEP NORM")
# 1. Kanaal instellingen uitlezen
huidige_status = {}
kanaal = instellingen["kanaal"]  # Bijv. 'CHAN1'
huidige_status["volt_per_div"] = scope.query(f":{kanaal}:SCAL?").strip()
huidige_status["display"] = scope.query(f":{kanaal}:DISP?").strip()

# 2. Tijdbasis uitlezen
huidige_status["tijd_per_div"] = scope.query(":TIM:SCAL?").strip()

# 3. Trigger instellingen uitlezen
huidige_status["trig_mode"] = scope.query(":TRIG:MODE?").strip()
huidige_status["trig_level"] = scope.query(":TRIG:PULS:LEV?").strip()
huidige_status["trig_sweep"] = scope.query(":TRIG:SWEEP?").strip()

# Netjes printen naar je scherm
print("\n--- ACTUELE SCOOP STATUS ---")
for sleutel, waarde in huidige_status.items():
    print(f"{sleutel:<15} : {waarde}")

# --- 3. Het Wachten (Verbeterde Logica) ---
print("Scope wordt scherpgesteld...")


print("Wachten op fysieke trigger (negatieve piek)...")
print("Kijk op de scope: staat er 'WAIT' bovenin? Stuur nu je signaal.")

start_time = time.time()
timeout = 120.0  # We wachten maximaal 30 seconden
triggered = False
data_dict = {}
while time.time() - start_time < Nmeting:
    start_timeout_time = time.time()
    scope.write(":SING")

    # Wacht even zodat de scope van 'STOP' naar 'WAIT' kan gaan
    time.sleep(1.0)
    while (time.time() - start_timeout_time) < timeout:
        # Vraag de status op
        status = scope.query(":TRIG:STAT?").strip()

        # DEBUG: print(f"Status: {status}")

        # We stoppen pas als de status TD (Triggered) of STOP is
        if status in ["TD", "STOP"]:
            # Dubbele check: soms zegt hij STOP terwijl hij nog niet klaar is
            time.sleep(0.5)
            if scope.query(":TRIG:STAT?").strip() in ["TD", "STOP"]:
                print(f"Trigger gedetecteerd! Status: {status}")
                triggered = True
                break

        time.sleep(0.1)

    if not triggered:
        print(
            "TIMEOUT: De scope is nooit getriggerd. De puls was te klein of het level staat verkeerd."
        )
        scope.close()
        exit()

    # --- 4. Data ophalen (Alleen als getriggerd) ---
    print("Data downloaden...")
    scope.write(":WAV:SOUR CHAN1")
    scope.write(":WAV:MODE NORM")
    scope.write(":WAV:FORM BYTE")
    scope.write(":WAV:RES")
    scope.write(":WAV:BEG")

    pre = scope.query(":WAV:PRE?").split(",")
    raw_bytes = scope.query_binary_values(
        ":WAV:DATA?", datatype="B", container=np.array
    )

    if raw_bytes.size > 0:
        # Berekening
        y_inc, y_orig, y_ref = float(pre[7]), float(pre[8]), float(pre[9])
        x_inc, x_orig, x_ref = float(pre[4]), float(pre[5]), float(pre[6])

        voltages = (raw_bytes.astype(float) - y_ref - y_orig) * y_inc
        times = (np.arange(len(raw_bytes)) - x_ref) * x_inc + x_orig
        # We maken een dictionary van de data
        meting_resultaat = {
            "meting_nummer": aantalpieken + 1,
            "tijdstempel": time.strftime("%H:%M:%S"),
            "piekwaarde": float(
                np.min(voltages)
            ),  # float() zorgt dat het JSON-vriendelijk is
            "tijd_as": times.tolist(),
            "voltage_as": voltages.tolist(),
        }
        sessie_data["metingen"].append(meting_resultaat)

        print(f"Succes! Piekwaarde: {np.min(voltages):.4f} V")

        aantalpieken += 1
        print(aantalpieken)

    else:
        print("Data transfer mislukt.")

scope.close()
# Maak een DataFrame (tabel)

# Opslaan. Gebruik sep=';' als je een Nederlandse Excel hebt.
bestandsnaam = input(f"Naam bestand:")
filename = f"{bestandsnaam}.JSON"
with open(filename, "w") as f:
    # indent=4 maakt het bestand leesbaar voor mensen (mooie enters en spaties)
    json.dump(sessie_data, f, indent=4)

print(f"Data succesvol opgeslagen in: {bestandsnaam}")
plt.plot(times * 1e6, voltages)
plt.xlabel("Tijd (us)")
plt.ylabel("Voltage (V)")
plt.grid(True)
plt.show()
