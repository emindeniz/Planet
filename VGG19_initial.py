import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)
import os
from sklearn.preprocessing import MultiLabelBinarizer, MinMaxScaler


import tensorflow as tf
from keras.callbacks import ModelCheckpoint, EarlyStopping
from keras.layers import Dropout, Flatten, Dense,BatchNormalization, GaussianNoise, Activation
from keras.models import Sequential
from keras import backend as K
import gc
from pathlib import Path
from six.moves import cPickle as pickle
from keras import optimizers
from sklearn.metrics import fbeta_score, accuracy_score
from sklearn.model_selection import KFold
from skimage import io, transform
import operator

def custom_loss(y_true,y_pred):
    top = -K.sum(K.batch_dot(y_true,y_pred,axes=1),axis=0)
    term1 = 0.2*K.sum(K.sum(y_true,axis=0,keepdims=False),axis=0,keepdims=False)
    term2 =0.8*K.sum(K.sum(y_pred,axis=0,keepdims=False),axis=0,keepdims=False)
    return top/(term1+term2+K.epsilon())


def generate_predictions_file(probabilities, thresholds,label_list):


    predictions_labels = []
    for prob in probabilities:
        labels = [label_list[i] for i, value in enumerate(prob) if value > thresholds[i]]
        predictions_labels.append(' '.join(labels))

    # Prepare to write predictions to file
    image_files = os.listdir('C:/planet/test-jpg/')

    predictions_df_dict = {'image_name': [w.replace('.jpg', '') for w in image_files],
                       'tags': ['' for i in range(len(image_files))],
                       }
    predictions_df = pd.DataFrame.from_dict(predictions_df_dict)
    predictions_df.set_index('image_name', drop=True, inplace=True)
    predictions_df.loc[[w.replace('.jpg', '') for w in image_files], 'tags'] = predictions_labels
    predictions_df.to_csv('predictions_single.csv', encoding='utf-8', index=True)

    return

def generate_predictions_file_global_thre(probabilities, threshold_alternative,label_list):


    predictions_labels = []
    for prob in probabilities:
        labels = [label_list[i] for i, value in enumerate(prob) if value > threshold_alternative]
        predictions_labels.append(' '.join(labels))

    # Prepare to write predictions to file
    image_files = os.listdir('C:/planet/test-jpg/')

    predictions_df_dict = {'image_name': [w.replace('.jpg', '') for w in image_files],
                       'tags': ['' for i in range(len(image_files))],
                       }
    predictions_df = pd.DataFrame.from_dict(predictions_df_dict)
    predictions_df.set_index('image_name', drop=True, inplace=True)
    predictions_df.loc[[w.replace('.jpg', '') for w in image_files], 'tags'] = predictions_labels
    predictions_df.to_csv('predictions_single.csv', encoding='utf-8', index=True)

    return


def f2_score(y_true, y_pred):
    y_true, y_pred, = np.array(y_true), np.array(y_pred)
    return fbeta_score(y_true, y_pred, beta=2, average='samples')


def find_f2score_threshold_global(p_valid, y_valid, try_all=False, verbose=False):
    best = 0
    best_score = -1
    totry = np.arange(0,1,0.05) if try_all is False else np.unique(p_valid)
    for t in totry:
        score = f2_score(y_valid, p_valid > t)
        if score > best_score:
            best_score = score
            best = t
    if verbose is True:
        print('Best score: ', round(best_score, 5), ' @ threshold =', best)
    return best

def find_fbetascore_threshold_class(p_valid, y_valid, try_all=False):
    best = [0]*p_valid.shape[1]
    best_score = [-1]*p_valid.shape[1]

    totry = np.arange(0,1,0.05) if try_all is False else np.unique(p_valid)

    for i in range(p_valid.shape[1]):
        for t in totry:
            score = fbeta_score(y_valid[:,i], p_valid[:,i] > t, beta=2, average='binary')
            if score > best_score[i]:
                best_score[i] = score
                best[i] = t

    best = [round(t,3) for t in best]
    return best

def load_images(tag,allimage_names,type,arch,augmented,image_folder,norm,filetype,image_size,channels):
    sess = tf.Session()
    K.set_session(sess)

    pickle_file = 'C:/planet/Pickle_files/' + tag + '-'+type+'_' +arch+ '_augmented_'+str(augmented)+'_norm_'+str(norm)+filetype+'_size'+str(image_size)+'_chan'+str(channels)+'.pickle'
    if Path(pickle_file).is_file():
        with open(pickle_file, 'rb') as f:
            save = pickle.load(f)
            dataset = save['dataset']
            labels = save['labels']
            del save  # hint to help gc free up memory
    else:
        if arch == 'Inception_V3':
            dataset = np.ndarray((allimage_names.shape[0], 2048), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)
        elif arch == 'Resnet':
            dataset = np.ndarray((allimage_names.shape[0], 2,2, 2048), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)
        elif arch == 'VGG19':
            dataset = np.ndarray((allimage_names.shape[0], 4,4,512), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)
        elif arch == 'VGG16':
            dataset = np.ndarray((allimage_names.shape[0], 4, 4, 512), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)
        elif arch == 'Xception':
            dataset = np.ndarray((allimage_names.shape[0],2048), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)
        else:
            dataset = np.ndarray((allimage_names.shape[0], image_size, image_size, channels), dtype=np.float32)
            labels = np.ndarray((allimage_names.shape[0], 17), dtype=np.int32)

        batch_size = 70000
        for i in range(0,allimage_names.shape[0],batch_size):
            df = allimage_names[i:i+batch_size]
            dataset_batch = np.ndarray((df.shape[0], image_size, image_size, channels), dtype=np.float32)
            labels_batch = np.ndarray((df.shape[0], 17), dtype=np.int32)
            num_images = 0
            for row in df.itertuples():
                image_file = image_folder + dict(row._asdict())['image_name'] + filetype
                try:
                    image_data = io.imread(image_file).astype(float)
                    image_data = transform.resize(image_data, (image_size, image_size))
                    if filetype == '.jpg' and norm == 'divide':
                        dataset_batch[num_images, :, :, :] = image_data / 255.0
                    elif filetype == '.jpg' and norm == 'globalmm':
                        image_min = np.min(image_data[:,:,0:channels])
                        image_max = np.max(image_data[:,:,0:channels])
                        dataset_batch[num_images, :, :, :] = (image_data-image_min)/(image_max-image_min)
                    elif filetype == '.jpg' and norm == 'globalmm255':
                        image_min = np.min(image_data[:,:,0:channels])
                        image_max = np.max(image_data[:,:,0:channels])
                        dataset_batch[num_images, :, :, :] = 255*(image_data[:,:,0:channels]-image_min)/(image_max-image_min)
                    elif filetype == '.jpg' and norm == 'global255':
                        image_data[:, :, 0] = MinMaxScaler(feature_range=(0, 255)).fit_transform(image_data[:, :, 0])
                        image_data[:, :, 1] = MinMaxScaler(feature_range=(0, 255)).fit_transform(image_data[:, :, 1])
                        image_data[:, :, 2] = MinMaxScaler(feature_range=(0, 255)).fit_transform(image_data[:, :, 2])
                        dataset_batch[num_images, :, :, :] = image_data
                    else:
                        dataset_batch[num_images, :, :, :] = image_data

                    if type=='predictions':
                        labels_batch[num_images]=1
                    else:
                        labels_batch[num_images] = row[3:22]
                    num_images = num_images + 1
                    del image_data
                except IOError as e:
                    print('Could not read:', image_file, ':', e, '- it\'s ok, skipping.')

            if arch =='Resnet':
                from keras.applications.resnet50 import ResNet50, preprocess_input
                dataset_batch = ResNet50(weights='imagenet', include_top=False).predict(preprocess_input(dataset_batch))
            if arch =='Inception_V3':
                from keras.applications.inception_v3 import InceptionV3, preprocess_input
                dataset_batch = InceptionV3(weights='imagenet', include_top=False,pooling='avg').predict(preprocess_input(dataset_batch))
            if arch =='VGG19':
                from keras.applications.vgg19 import VGG19, preprocess_input
                dataset_batch = VGG19(weights='imagenet', include_top=False).predict(preprocess_input(dataset_batch))
            if arch =='VGG16':
                from keras.applications.vgg16 import VGG16, preprocess_input
                dataset_batch = VGG16(weights='imagenet', include_top=False).predict(preprocess_input(dataset_batch))
            if arch == 'Xception':
                from keras.applications.xception import Xception, preprocess_input
                dataset_batch = Xception(weights='imagenet', include_top=False,pooling='avg').predict(preprocess_input(dataset_batch))


            dataset[i:i+batch_size] = dataset_batch
            labels[i:i + batch_size] = labels_batch
            del dataset_batch
            print('Processed',i)

        try:
            f = open(pickle_file, 'wb')
            save = {
                'dataset': dataset,
                'labels': labels,
            }
            pickle.dump(save, f, pickle.HIGHEST_PROTOCOL)
            f.close()
        except Exception as e:
            print('Unable to save data to', pickle_file, ':', e)
            raise


    print('Full tensor for '+type+':', dataset.shape)
    print('Label shape:',labels.shape)
    print('label distribution:', np.mean(labels))

    return dataset,labels


def run_model(df,proportions,arch,tag,tag_weights,augmented,image_folder,norm,filetype,size,channels,label_list):


    data_set, data_labels = load_images('all', df, 'all', arch,augmented,image_folder,norm,filetype,size,channels)
    print(data_set.shape)
    print(data_labels.shape)

    ones = proportions
    zeros = [100 - item for item in ones]

    nsplit=5
    kf = KFold(n_splits=nsplit)
    fold = 0
    for train_index, test_index in kf.split(data_set):
        train_set, train_labels = data_set[train_index], data_labels[train_index]
        valid_set, valid_labels = data_set[test_index], data_labels[test_index]


        # Create the model
        model = Sequential()
        model.add(Flatten(input_shape=data_set.shape[1:],name='one'))
        model.add(Dense(1024, activation='relu', name='three'))
        model.add(Dense(17, name='seven'))
        model.add(Activation('sigmoid', name='nine'))
        model.summary()

        rms_optimizer = optimizers.RMSprop(lr=0.001)
        model.compile(loss='binary_crossentropy', optimizer=rms_optimizer, metrics=['accuracy'])

        weight_file = 'C:/planet/saved_models/weights.best_' + tag + '_' + arch + '_' + str(fold) + '.hdf5'

        checkpointer = ModelCheckpoint(filepath=weight_file,
                                       verbose=1, save_best_only=True)

        model.fit(train_set, train_labels,
                         validation_data=(valid_set, valid_labels),
                         epochs=5, batch_size=1024,
                         callbacks=[checkpointer], verbose=2)


        fold+=1
        if fold==1:
            break

    # Performance assessment
    nsplit = 1
    data_probs = np.ndarray((nsplit, valid_set.shape[0], valid_labels.shape[1]), dtype=np.float32)

    for fold in range(nsplit):

        weight_file = 'C:/planet/saved_models/weights.best_' + tag + '_' + arch + '_' + str(fold) + '.hdf5'

        ### TODO: Load the model weights with the best validation loss.
        model.load_weights(weight_file)

        #Predict the dataset for this fold
        data_probs[fold,:,:] =  model.predict(valid_set)

    data_probs = np.mean(data_probs,0)

    thresholds_class = find_fbetascore_threshold_class(data_probs,valid_labels)
    threshold_global = find_f2score_threshold_global(data_probs,valid_labels)

    predictions = []
    for Resnet_prob in data_probs:
        one_hot_labels = [1 if value > threshold_global else 0 for i, value in enumerate(Resnet_prob) ]
        predictions.append(one_hot_labels)

    # fbeta_score throws a confusing error if inputs are not numpy arrays
    y_true, y_pred, = np.array(valid_labels), np.array(predictions)

    scores = {}
    for i in range(y_true.shape[1]):
        scores[label_list[i]]=(accuracy_score(y_true[:,i],y_pred[:,i]),fbeta_score(y_true[:,i], y_pred[:,i], beta=2, average='binary'))
    print(sorted(scores.items(), key=operator.itemgetter(0)))


    # We need to use average='samples' here, any other average method will generate bogus results
    train_score = fbeta_score(y_true, y_pred, beta=2, average='samples')
    print('Training score with global threshold:(samples)',train_score)
    # We need to use average='samples' here, any other average method will generate bogus results
    train_score = fbeta_score(y_true, y_pred, beta=2, average='micro')
    print('Training score(micro) with global threshold(micro):',train_score)


    predictions = []
    for Resnet_prob in data_probs:
        one_hot_labels = [1 if value > thresholds_class[i] else 0 for i, value in enumerate(Resnet_prob) ]
        predictions.append(one_hot_labels)

    # fbeta_score throws a confusing error if inputs are not numpy arrays
    y_true, y_pred, = np.array(valid_labels), np.array(predictions)

    scores = {}
    for i in range(y_true.shape[1]):
        scores[label_list[i]]=(accuracy_score(y_true[:,i],y_pred[:,i]),fbeta_score(y_true[:,i], y_pred[:,i], beta=2, average='binary'))
    print(sorted(scores.items(), key=operator.itemgetter(0)))


    # We need to use average='samples' here, any other average method will generate bogus results
    train_score = fbeta_score(y_true, y_pred, beta=2, average='samples')
    print('Training score with class threshold:(samples)',train_score)

    train_score = fbeta_score(y_true, y_pred, beta=2, average='micro')
    print('Training score with class threshold:(micro)',train_score)



    #Save the results:
    np.savez('Results_'+tag+'_'+arch+'.npz', data_probs=data_probs, data_labels=data_labels)

    #Save the calculated thresholds
    np.savez('thresholds_class.npz', thresholds=thresholds_class)

    #Save the calculated thresholds
    np.savez('thresholds_global.npz', thresholds=threshold_global)


    model_json =  model.to_json()
    model_file = 'C:/planet/saved_models/model_'+tag+'_'+arch+'.json'
    with open(model_file, 'w+') as json_file:
        json_file.write(model_json)

    sess = K.get_session()
    if sess:
        sess.close()
    gc.collect()

    return


def main():

    tag = 'all'
    arch = 'VGG19'
    augmented = 0
    image_folder = 'C:/planet/train-jpg/'
    norm = 'none'
    size = 128
    channels = 3
    filetype = '.jpg'

    df = pd.read_csv('train_v2.csv')
    print(df.info())
    print(df[1:5])

    # Build list with unique labels
    label_list = []
    for tag_str in df.tags.values:
        labels = tag_str.split(' ')
        for label in labels:
            if label not in label_list:
                label_list.append(label)
    print(label_list)

    # Add onehot features for every label
    for label in label_list:
        df[label] = df['tags'].apply(lambda x: 1 if label in x.split(' ') else 0)
    # Display head
    print(df.info())
    df.head()

    label_list = ['haze','primary','agriculture','clear', 'water', 'habitation', 'road', 'cultivation','slash_burn','cloudy','partly_cloudy', 'conventional_mine',
               'bare_ground','artisinal_mine', 'blooming', 'selective_logging', 'blow_down', ]
    df = df.sample(frac=1)

    label_counts = df[label_list].sum().tolist()
    proportions = [int(count/df.shape[0]*100)+1 for count in label_counts]


    all_tags = [item for sublist in list(df['tags'].apply(lambda row: row.split(" ")).values) for item in sublist]
    print('total of {} non-unique tags in all training images'.format(len(all_tags)))
    print('average number of labels per image {}'.format(1.0 * len(all_tags) / df.shape[0]))
    tags_counted_and_sorted = pd.DataFrame({'tag': all_tags}).groupby('tag').size()
    print(tags_counted_and_sorted[label_list])
    tag_counts = tags_counted_and_sorted[label_list].tolist()
    tag_weights = [int(len(all_tags)/count) for count in tag_counts]

    run_model(df,proportions,arch,tag,tag_weights,augmented,image_folder,norm,filetype,size,channels,label_list)

    return



if __name__ == "__main__":
    main()


