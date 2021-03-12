# Training script for the SRNet. Refer README for instructions.
# author: Niwhskal
# github : https://github.com/Niwhskal/SRNet

import numpy as np
import os
import torch
import torchvision.transforms
from utils import *
import cfg
from tqdm import tqdm
import torchvision.transforms.functional as F
from skimage.transform import resize
from skimage import io
from model import Generator, Discriminator, Vgg19
from torchvision import models, transforms, datasets
from loss import build_generator_loss, build_discriminator_loss
from datagen import datagen_srnet, example_dataset, To_tensor
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard import SummaryWriter


def requires_grad(model, flag=True):
    for p in model.parameters():
        p.requires_grad = flag

def custom_collate(batch):

    i_t_batch, i_s_batch = [], []
    t_sk_batch, t_t_batch, t_b_batch, t_f_batch = [], [], [], []
    mask_t_batch = []

    w_sum = 0

    for item in batch:

        t_b= item[4]
        h, w = t_b.shape[:2]
        scale_ratio = cfg.data_shape[0] / h
        w_sum += int(w * scale_ratio)

    to_h = cfg.data_shape[0]
    to_w = w_sum // cfg.batch_size
    to_w = int(round(to_w / 8)) * 8
    to_scale = (to_h, to_w)

    for item in batch:

        i_t, i_s, t_sk, t_t, t_b, t_f, mask_t = item


        i_t = resize(i_t, to_scale, preserve_range=True)
        i_s = resize(i_s, to_scale, preserve_range=True)
        t_sk = np.expand_dims(resize(t_sk, to_scale, preserve_range=True), axis = -1)
        t_t = resize(t_t, to_scale, preserve_range=True)
        t_b = resize(t_b, to_scale, preserve_range=True)
        t_f = resize(t_f, to_scale, preserve_range=True)
        mask_t = np.expand_dims(resize(mask_t, to_scale, preserve_range=True), axis = -1)


        i_t = i_t.transpose((2, 0, 1))
        i_s = i_s.transpose((2, 0, 1))
        t_sk = t_sk.transpose((2, 0, 1))
        t_t = t_t.transpose((2, 0, 1))
        t_b = t_b.transpose((2, 0, 1))
        t_f = t_f.transpose((2, 0, 1))
        mask_t = mask_t.transpose((2, 0, 1))

        i_t_batch.append(i_t)
        i_s_batch.append(i_s)
        t_sk_batch.append(t_sk)
        t_t_batch.append(t_t)
        t_b_batch.append(t_b)
        t_f_batch.append(t_f)
        mask_t_batch.append(mask_t)

    i_t_batch = np.stack(i_t_batch)
    i_s_batch = np.stack(i_s_batch)
    t_sk_batch = np.stack(t_sk_batch)
    t_t_batch = np.stack(t_t_batch)
    t_b_batch = np.stack(t_b_batch)
    t_f_batch = np.stack(t_f_batch)
    mask_t_batch = np.stack(mask_t_batch)

    i_t_batch = torch.from_numpy(i_t_batch.astype(np.float32) / 127.5 - 1.)
    i_s_batch = torch.from_numpy(i_s_batch.astype(np.float32) / 127.5 - 1.)
    t_sk_batch = torch.from_numpy(t_sk_batch.astype(np.float32) / 255.)
    t_t_batch = torch.from_numpy(t_t_batch.astype(np.float32) / 127.5 - 1.)
    t_b_batch = torch.from_numpy(t_b_batch.astype(np.float32) / 127.5 - 1.)
    t_f_batch = torch.from_numpy(t_f_batch.astype(np.float32) / 127.5 - 1.)
    mask_t_batch =torch.from_numpy(mask_t_batch.astype(np.float32) / 255.)


    return [i_t_batch, i_s_batch, t_sk_batch, t_t_batch, t_b_batch, t_f_batch, mask_t_batch]

def clip_grad(model):

    for h in model.parameters():
        h.data.clamp_(-0.01, 0.01)

def main():
    train_name = get_train_name()

    # Initialize log folder
    if not os.path.exists(os.path.join(cfg.checkpoint_savedir, train_name)):
        os.makedirs(os.path.join(cfg.checkpoint_savedir, train_name))

    # Init Tensorboard
    writer = SummaryWriter(os.path.join(cfg.checkpoint_savedir, train_name))

    os.environ['CUDA_VISIBLE_DEVICES'] = str(cfg.gpu)

    print_log('Initializing SRNET', content_color = PrintColor['yellow'])

    train_data = datagen_srnet(cfg)

    train_data = DataLoader(dataset = train_data, batch_size = cfg.batch_size, shuffle = False, collate_fn = custom_collate,  pin_memory = True)

    trfms = To_tensor()
    example_data = example_dataset(transform = trfms)

    example_loader = DataLoader(dataset = example_data, batch_size = 1, shuffle = False)

    print_log('training start.', content_color = PrintColor['yellow'])

    G = Generator(in_channels = 3).cuda()

    D1 = Discriminator(in_channels = 6).cuda()

    D2 = Discriminator(in_channels = 6).cuda()

    vgg_features = Vgg19().cuda()

    G_solver = torch.optim.Adam(G.parameters(), lr=cfg.learning_rate, betas = (cfg.beta1, cfg.beta2))
    D1_solver = torch.optim.Adam(D1.parameters(), lr=cfg.learning_rate, betas = (cfg.beta1, cfg.beta2))
    D2_solver = torch.optim.Adam(D2.parameters(), lr=cfg.learning_rate, betas = (cfg.beta1, cfg.beta2))

    #g_scheduler = torch.optim.lr_scheduler.MultiStepLR(G_solver, milestones=[30, 200], gamma=0.5)

    #d1_scheduler = torch.optim.lr_scheduler.MultiStepLR(D1_solver, milestones=[30, 200], gamma=0.5)

    #d2_scheduler = torch.optim.lr_scheduler.MultiStepLR(D2_solver, milestones=[30, 200], gamma=0.5)

    try:

      checkpoint = torch.load(cfg.ckpt_path)
      G.load_state_dict(checkpoint['generator'])
      D1.load_state_dict(checkpoint['discriminator1'])
      D2.load_state_dict(checkpoint['discriminator2'])
      G_solver.load_state_dict(checkpoint['g_optimizer'])
      D1_solver.load_state_dict(checkpoint['d1_optimizer'])
      D2_solver.load_state_dict(checkpoint['d2_optimizer'])

      '''
      g_scheduler.load_state_dict(checkpoint['g_scheduler'])
      d1_scheduler.load_state_dict(checkpoint['d1_scheduler'])
      d2_scheduler.load_state_dict(checkpoint['d2_scheduler'])
      '''

      print('Resuming after loading...')

    except FileNotFoundError:

      print('checkpoint not found')
      pass

    requires_grad(G, False)

    requires_grad(D1, True)
    requires_grad(D2, True)


    disc_loss_val = 0
    gen_loss_val = 0
    grad_loss_val = 0


    trainiter = iter(train_data)
    example_iter = iter(example_loader)

    K = torch.nn.ZeroPad2d((0, 1, 1, 0))

    for step in tqdm(range(cfg.max_iter)):

        D1_solver.zero_grad()
        D2_solver.zero_grad()

        if ((step+1) % cfg.save_ckpt_interval == 0):

            torch.save(
                {
                    'generator': G.state_dict(),
                    'discriminator1': D1.state_dict(),
                    'discriminator2': D2.state_dict(),
                    'g_optimizer': G_solver.state_dict(),
                    'd1_optimizer': D1_solver.state_dict(),
                    'd2_optimizer': D2_solver.state_dict(),
                    #'g_scheduler' : g_scheduler.state_dict(),
                    #'d1_scheduler':d1_scheduler.state_dict(),
                    #'d2_scheduler':d2_scheduler.state_dict(),
                },
                os.path.join(cfg.checkpoint_savedir, train_name, 'train_step-{}.model'.format(step+1))
            )

        try:

          i_t, i_s, t_sk, t_t, t_b, t_f, mask_t = trainiter.next()

        except StopIteration:

          trainiter = iter(train_data)
          i_t, i_s, t_sk, t_t, t_b, t_f, mask_t = trainiter.next()

        i_t = i_t.cuda()
        i_s = i_s.cuda()
        t_sk = t_sk.cuda()
        t_t = t_t.cuda()
        t_b = t_b.cuda()
        t_f = t_f.cuda()
        mask_t = mask_t.cuda()

        #inputs = [i_t, i_s]
        labels = [t_sk, t_t, t_b, t_f]

        o_sk, o_t, o_b, o_f = G(i_t, i_s, (i_t.shape[2], i_t.shape[3])) #Adding dim info

        o_sk = K(o_sk)
        o_t = K(o_t)
        o_b = K(o_b)
        o_f = K(o_f)

        #print(o_sk.shape, o_t.shape, o_b.shape, o_f.shape)
        #print('------')
        #print(i_s.shape)

        i_db_true = torch.cat((t_b, i_s), dim = 1)
        i_db_pred = torch.cat((o_b, i_s), dim = 1)

        i_df_true = torch.cat((t_f, i_t), dim = 1)
        i_df_pred = torch.cat((o_f, i_t), dim = 1)

        o_db_true = D1(i_db_true)
        o_db_pred = D1(i_db_pred)

        o_df_true = D2(i_df_true)
        o_df_pred = D2(i_df_pred)

        i_vgg = torch.cat((t_f, o_f), dim = 0)

        out_vgg = vgg_features(i_vgg)

        db_loss = build_discriminator_loss(o_db_true,  o_db_pred)

        df_loss = build_discriminator_loss(o_df_true, o_df_pred)

        db_loss.backward()
        df_loss.backward()

        D1_solver.step()
        D2_solver.step()

        #d1_scheduler.step()
        #d2_scheduler.step()

        clip_grad(D1)
        clip_grad(D2)


        if ((step+1) % 1 == 0):

            requires_grad(G, True)

            requires_grad(D1, False)
            requires_grad(D2, False)

            G_solver.zero_grad()

            o_sk, o_t, o_b, o_f = G(i_t, i_s, (i_t.shape[2], i_t.shape[3]))

            o_sk = K(o_sk)
            o_t = K(o_t)
            o_b = K(o_b)
            o_f = K(o_f)

            #print(o_sk.shape, o_t.shape, o_b.shape, o_f.shape)
            #print('------')
            #print(i_s.shape)

            i_db_true = torch.cat((t_b, i_s), dim = 1)
            i_db_pred = torch.cat((o_b, i_s), dim = 1)

            i_df_true = torch.cat((t_f, i_t), dim = 1)
            i_df_pred = torch.cat((o_f, i_t), dim = 1)

            o_db_pred = D1(i_db_pred)

            o_df_pred = D2(i_df_pred)

            i_vgg = torch.cat((t_f, o_f), dim = 0)

            out_vgg = vgg_features(i_vgg)

            out_g = [o_sk, o_t, o_b, o_f, mask_t]

            out_d = [o_db_pred, o_df_pred]

            g_loss, detail = build_generator_loss(out_g, out_d, out_vgg, labels)

            g_loss.backward()

            G_solver.step()

            #g_scheduler.step()

            requires_grad(G, False)

            requires_grad(D1, True)
            requires_grad(D2, True)

        if ((step+1) % cfg.write_log_interval == 0):

            writer.add_scalar('Loss/Gen', g_loss.item(), step+1)
            writer.add_scalar('Loss/D_bg', db_loss.item(), step+1)
            writer.add_scalar('Loss/D_fus', df_loss.item(), step+1)
            print('Iter: {}/{} | Gen: {} | D_bg: {} | D_fus: {}'.format(step+1, cfg.max_iter, g_loss.item(), db_loss.item(), df_loss.item()))

        if ((step+1) % cfg.gen_example_interval == 0):

            savedir = os.path.join(cfg.example_result_dir, train_name, 'iter-' + str(step+1).zfill(len(str(cfg.max_iter))))

            with torch.no_grad():

                try:

                  inp = example_iter.next()

                except StopIteration:

                  example_iter = iter(example_loader)
                  inp = example_iter.next()

                i_t = inp[0].cuda()
                i_s = inp[1].cuda()
                name = str(inp[2][0])

                o_sk, o_t, o_b, o_f = G(i_t, i_s, (i_t.shape[2], i_t.shape[3]))

                o_sk = o_sk.squeeze(0).to('cpu')
                o_t = o_t.squeeze(0).to('cpu')
                o_b = o_b.squeeze(0).to('cpu')
                o_f = o_f.squeeze(0).to('cpu')

                if not os.path.exists(savedir):
                    os.makedirs(savedir)

                o_sk = F.to_pil_image(o_sk)
                o_t = F.to_pil_image((o_t + 1)/2)
                o_b = F.to_pil_image((o_b + 1)/2)
                o_f = F.to_pil_image((o_f + 1)/2)

                o_f.save(os.path.join(savedir, name + 'o_f.png'))
                o_sk.save(os.path.join(savedir, name + 'o_sk.png'))
                o_t.save(os.path.join(savedir, name + 'o_t.png'))
                o_b.save(os.path.join(savedir, name + 'o_b.png'))

if __name__ == '__main__':
    main()
