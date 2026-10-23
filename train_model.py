"""Train CropBot from a folder-per-class image dataset.

PlantVillage layout: datasets/PlantVillage/<crop>___<disease>/*.(jpg|png)
PlantDoc layout: set CROPBOT_DATASET_DIR to the directory containing its class folders.

PlantDoc is a small, field-photo benchmark; keep a held-out split and treat its
validation score as a development metric, not a guarantee on farm photos.
"""
import json
import os

import tensorflow as tf
from tensorflow.keras import layers

DATA = os.environ.get("CROPBOT_DATASET_DIR", os.path.join("datasets", "PlantVillage"))
OUT = os.environ.get("CROPBOT_OUTPUT_DIR", "models")
MODEL_FILE = os.environ.get("CROPBOT_MODEL_FILE", "plant_disease_model.keras")
CLASS_FILE = os.environ.get("CROPBOT_CLASS_FILE", "class_indices.json")
SIZE, BATCH, EPOCHS = 224, 16, int(os.environ.get("CROPBOT_EPOCHS", "20"))
os.makedirs(OUT, exist_ok=True)

if not os.path.isdir(DATA):
    raise SystemExit(f"Dataset directory not found: {DATA}")

has_official_split = os.path.isdir(os.path.join(DATA, "train")) and os.path.isdir(os.path.join(DATA, "test"))
if has_official_split:
    train = tf.keras.utils.image_dataset_from_directory(
        os.path.join(DATA, "train"), image_size=(SIZE, SIZE), batch_size=BATCH,
        label_mode="categorical",
    )
    valid = tf.keras.utils.image_dataset_from_directory(
        os.path.join(DATA, "test"), class_names=train.class_names,
        image_size=(SIZE, SIZE), batch_size=BATCH, label_mode="categorical",
    )
else:
    train = tf.keras.utils.image_dataset_from_directory(
        DATA, validation_split=0.2, subset="training", seed=42,
        image_size=(SIZE, SIZE), batch_size=BATCH, label_mode="categorical",
    )
    valid = tf.keras.utils.image_dataset_from_directory(
        DATA, validation_split=0.2, subset="validation", seed=42,
        image_size=(SIZE, SIZE), batch_size=BATCH, label_mode="categorical",
    )

def normalize_class(name):
    """Convert dataset folder labels to the app's stable crop___condition form."""
    original = name.strip()
    name = original.replace(" ", "_")
    if "___" in name:
        crop, condition = name.split("___", 1)
    else:
        # PlantDoc uses labels like "Tomato leaf bacterial spot" rather than
        # machine-readable Crop___Disease folder names.
        lower = original.lower().replace("_", " ").strip()
        crop_aliases = {
            "bell pepper": "Bell_pepper", "soyabean": "Soybean",
            "blueberry": "Blueberry", "raspberry": "Raspberry",
            "strawberry": "Strawberry", "apple": "Apple", "cherry": "Cherry",
            "corn": "Corn", "peach": "Peach", "potato": "Potato",
            "squash": "Squash", "tomato": "Tomato", "grape": "Grape",
        }
        crop_match = next((crop for crop in sorted(crop_aliases, key=len, reverse=True)
                           if lower == crop or lower.startswith(crop + " ")), None)
        if crop_match:
            crop = crop_aliases[crop_match]
            condition = lower[len(crop_match):].strip()
            condition = condition.removesuffix(" leaf").removesuffix(" leaves").strip()
            if condition in ("", "leaf", "leaves"):
                condition = "healthy"
            elif condition == "mold":
                condition = "leaf mold"
            elif condition == "yellow virus":
                condition = "yellow leaf curl virus"
            elif condition.startswith("leaf ") and condition not in ("leaf spot", "leaf blight"):
                condition = condition[5:]
            if condition == "yellow virus":
                condition = "yellow leaf curl virus"
            condition = condition or "healthy"
            return f"{crop}___{'_'.join(condition.split())}"
        # Legacy PlantVillage folders use two underscores before the crop/disease separator.
        parts = name.split("__")
        if len(parts) >= 3:
            crop, condition = "_".join(parts[:-1]), parts[-1]
        else:
            crop, _, condition = name.partition("_")
    crop = "_".join(crop.strip("_").split("_"))
    condition = "_".join(condition.strip("_").split("_")) or "Unknown"
    return f"{crop}___{condition}"

names = [normalize_class(n) for n in train.class_names]
if len(set(names)) != len(names):
    raise SystemExit("Dataset class names collide after normalization; rename the class folders first.")
class_path = os.path.join(OUT, CLASS_FILE)
with open(class_path, "w", encoding="utf-8") as file:
    json.dump({i: name for i, name in enumerate(names)}, file, indent=2)

augment = tf.keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.12),
    layers.RandomZoom(0.15),
    layers.RandomContrast(0.12),
])
base = tf.keras.applications.MobileNetV2(
    input_shape=(SIZE, SIZE, 3), include_top=False, weights="imagenet"
)
base.trainable = False
inputs = tf.keras.Input((SIZE, SIZE, 3))
x = augment(inputs)
x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
x = base(x, training=False)
x = layers.GlobalAveragePooling2D()(x)
x = layers.Dropout(0.3)(x)
outputs = layers.Dense(len(names), activation="softmax")(x)
model = tf.keras.Model(inputs, outputs)
model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
              loss="categorical_crossentropy", metrics=["accuracy"])

model_path = os.path.join(OUT, MODEL_FILE)
callbacks = [
    tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=4, mode="max", restore_best_weights=True),
    tf.keras.callbacks.ModelCheckpoint(model_path, monitor="val_accuracy", mode="max", save_best_only=True),
    tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", patience=2, factor=0.3, min_lr=1e-6),
]
train = train.prefetch(tf.data.AUTOTUNE)
valid = valid.prefetch(tf.data.AUTOTUNE)
history = model.fit(train, validation_data=valid, epochs=EPOCHS, callbacks=callbacks)
best_accuracy = max(history.history.get("val_accuracy", [0]))

# Fine-tune the last MobileNetV2 layers on the field photos at a low learning
# rate. BatchNorm stays frozen because the field dataset is relatively small.
model = tf.keras.models.load_model(model_path)
base = next(layer for layer in model.layers if isinstance(layer, tf.keras.Model) and len(layer.layers) > 100)
base.trainable = True
unfreeze = int(os.environ.get("CROPBOT_FINE_TUNE_LAYERS", "30"))
for layer in base.layers[:-unfreeze]:
    layer.trainable = False
for layer in base.layers:
    if isinstance(layer, layers.BatchNormalization):
        layer.trainable = False
model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
              loss="categorical_crossentropy", metrics=["accuracy"])
fine_callbacks = [
    tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=3, mode="max", restore_best_weights=True),
    tf.keras.callbacks.ModelCheckpoint(model_path, monitor="val_accuracy", mode="max",
                                       save_best_only=True, initial_value_threshold=best_accuracy),
    tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", patience=2, factor=0.3, min_lr=1e-7),
]
fine = model.fit(train, validation_data=valid,
                 epochs=int(os.environ.get("CROPBOT_FINE_TUNE_EPOCHS", "8")), callbacks=fine_callbacks)
best_accuracy = max(best_accuracy, max(fine.history.get("val_accuracy", [0])))
print(f"Saved {model_path} and {class_path}; best validation accuracy: {best_accuracy:.1%}")
