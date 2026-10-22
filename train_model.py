"""Train a compact MobileNetV2 leaf classifier. Run on a computer with TensorFlow installed.

Dataset layout: datasets/PlantVillage/<class-name>/*.(jpg|png)
"""
import json, os
import tensorflow as tf
from tensorflow.keras import layers

DATA = os.environ.get('CROPBOT_DATASET_DIR', os.path.join('datasets', 'PlantVillage'))
OUT = 'models'
SIZE, BATCH, EPOCHS = 224, 24, 12
os.makedirs(OUT, exist_ok=True)
train = tf.keras.utils.image_dataset_from_directory(DATA, validation_split=.2, subset='training', seed=42,
    image_size=(SIZE,SIZE), batch_size=BATCH, label_mode='categorical')
valid = tf.keras.utils.image_dataset_from_directory(DATA, validation_split=.2, subset='validation', seed=42,
    image_size=(SIZE,SIZE), batch_size=BATCH, label_mode='categorical')
def normalize_class(name):
    # PlantVillage mirrors use both Crop___Disease and Crop_Disease naming.
    if '___' in name:
        crop, disease = name.split('___', 1)
    else:
        crop, _, disease = name.partition('_')
    crop, disease = crop.strip('_'), disease.strip('_')
    return f'{crop}___{disease or "Unknown"}'

names = [normalize_class(n) for n in train.class_names]
with open(os.path.join(OUT,'class_indices.json'),'w',encoding='utf-8') as f:
    json.dump({i:n for i,n in enumerate(names)},f,indent=2)
augment = tf.keras.Sequential([layers.RandomFlip('horizontal'),layers.RandomRotation(.08),layers.RandomZoom(.1)])
base = tf.keras.applications.MobileNetV2(input_shape=(SIZE,SIZE,3),include_top=False,weights='imagenet')
base.trainable=False
inp=tf.keras.Input((SIZE,SIZE,3))
x=augment(inp)
x=tf.keras.applications.mobilenet_v2.preprocess_input(x)
x=base(x,training=False)
x=layers.GlobalAveragePooling2D()(x)
x=layers.Dropout(.25)(x)
out=layers.Dense(len(names),activation='softmax')(x)
model=tf.keras.Model(inp,out)
model.compile(optimizer='adam',loss='categorical_crossentropy',metrics=['accuracy'])
callbacks=[tf.keras.callbacks.EarlyStopping(patience=3,restore_best_weights=True),
 tf.keras.callbacks.ModelCheckpoint(os.path.join(OUT,'plant_disease_model.keras'),save_best_only=True)]
train=train.prefetch(tf.data.AUTOTUNE); valid=valid.prefetch(tf.data.AUTOTUNE)
model.fit(train,validation_data=valid,epochs=EPOCHS,callbacks=callbacks)
print('Saved model and class list in models/. Copy both to the Pi.')
